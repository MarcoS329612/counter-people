import asyncio
import io
import itertools
import socket
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib.resources import files
from types import FrameType

import segno
import uvicorn
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from people_counter.adapters.gemini_analyst import DEFAULT_GEMINI_MODELS, GeminiSceneAnalyst
from people_counter.adapters.scene_analyst import (
    DEFAULT_CLAUDE_MODEL,
    AnalystError,
    ClaudeSceneAnalyst,
    SceneAnalyst,
)
from people_counter.adapters.tunnel import CloudflareQuickTunnel, TunnelError
from people_counter.adapters.web_display import WebDisplay
from people_counter.bootstrap import CountPeople
from people_counter.domain.model import CapacityEvent, CapacityMonitor, Role, capacity_status
from people_counter.entrypoints.cli import bootstrap_from, build_parser
from people_counter.service_layer import services

STATIC = files(__package__) / "static"
PRESENTER_PAGE = (STATIC / "index.html").read_text()
PHONE_PAGE = (STATIC / "phone.html").read_text()
DEFAULT_CAPACITY = 40
ROOM_WIDE = {"event", "analysis"}  # feed items every phone sees, whatever its team
SECONDS_BETWEEN_DECISIONS = 15  # if the count hovers around the capacity, don't ask Claude on every crossing


@dataclass(frozen=True)
class FeedItem:
    id: int
    time: str
    kind: str  # "event", "analysis", "decision", "question" or "error"
    text: str
    role: Role | None = None  # decisions and questions belong to a team
    question: str | None = None


class Feed:
    """What happened in the room, for the presenter screen and the phones. Thread-safe."""

    def __init__(self, max_items: int = 500):
        self._items: deque[FeedItem] = deque(maxlen=max_items)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, kind: str, text: str, role: Role | None = None, question: str | None = None) -> FeedItem:
        with self._lock:
            item = FeedItem(next(self._ids), datetime.now().strftime("%H:%M:%S"), kind, text, role, question)
            self._items.append(item)
            return item

    def since(self, after: int) -> list[FeedItem]:
        with self._lock:
            return [item for item in self._items if item.id > after]


class QuestionLimits:
    """The tunnel URL is public: keep one person (or a leaked link) from spending the whole API budget."""

    def __init__(self, per_person_per_minute: int = 5, total_per_minute: int = 60, at_once: int = 4):
        self._per_person = per_person_per_minute
        self._total = total_per_minute
        self._asked: dict[str, deque[float]] = {}
        self._everyone: deque[float] = deque()
        self._lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(at_once)

    def allow(self, person: str) -> bool:
        now = time.monotonic()
        with self._lock:
            asked = self._asked.setdefault(person, deque())
            for times in (asked, self._everyone):
                while times and now - times[0] > 60:
                    times.popleft()
            if len(asked) >= self._per_person or len(self._everyone) >= self._total:
                return False
            asked.append(now)
            self._everyone.append(now)
            return True


class Question(BaseModel):
    role: Role
    question: str = Field(max_length=2000)
    client_id: str = Field(default="", max_length=64)


class Capacity(BaseModel):
    capacity: int = Field(ge=1, le=10_000)


def is_presenter(request: Request) -> bool:
    """The laptop itself. Requests through the tunnel also come from localhost, but Cloudflare marks them."""
    local = request.client is not None and request.client.host in {"127.0.0.1", "::1"}
    return local and "cf-connecting-ip" not in request.headers


def require_presenter(request: Request) -> None:
    if not is_presenter(request):
        raise HTTPException(status_code=403, detail="Solo desde la laptop del presentador.")


def create_app(
    count_people: CountPeople,
    analyst: SceneAnalyst | None = None,
    capacity: int = DEFAULT_CAPACITY,
    public_url: str | None = None,
) -> FastAPI:
    display = WebDisplay()
    monitor = CapacityMonitor(capacity)
    feed = Feed()
    limits = QuestionLimits()

    async def react(event: CapacityEvent) -> None:
        snapshot = display.latest()
        if analyst is None or snapshot is None:
            return
        try:
            image = await asyncio.to_thread(snapshot.clean_jpeg)
            decisions = await asyncio.to_thread(services.decide_for_each_team, analyst, image, event)
        except AnalystError as error:
            feed.add("error", f"No se pudieron generar las decisiones: {error}")
            return
        for role, decision in decisions.items():
            feed.add("decision", decision, role)

    async def watch_capacity() -> None:
        last_decision = -float(SECONDS_BETWEEN_DECISIONS)
        while not display.closed:
            snapshot = display.latest()
            if snapshot and (event := monitor.check(snapshot.occupancy.count)):
                if event.exceeded:
                    feed.add("event", f"Aforo rebasado: {event.count} personas, el aforo es {event.capacity}.")
                else:
                    feed.add("event", f"De vuelta dentro del aforo: {event.count} de {event.capacity}.")
                if time.monotonic() - last_decision >= SECONDS_BETWEEN_DECISIONS:
                    last_decision = time.monotonic()
                    asyncio.create_task(react(event))  # noqa: RUF006 - lives as long as the app, errors are handled inside
            await asyncio.sleep(0.5)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The counting loop blocks (camera + model), so it runs in its own thread.
        app.state.worker = threading.Thread(target=count_people, args=(display,), daemon=True)
        app.state.worker.start()
        watcher = asyncio.create_task(watch_capacity())
        yield
        display.close()
        watcher.cancel()
        app.state.worker.join(timeout=2)

    app = FastAPI(title="People counter", lifespan=lifespan)
    app.state.display = display

    @app.get("/", response_class=HTMLResponse, response_model=None)
    def index(request: Request) -> str | RedirectResponse:
        return PRESENTER_PAGE if is_presenter(request) else RedirectResponse("/m")

    @app.get("/m", response_class=HTMLResponse)
    def phone() -> str:
        return PHONE_PAGE

    @app.get("/api/occupancy")
    def occupancy() -> dict[str, int | bool | str | None]:
        snapshot = display.latest()
        count = snapshot.occupancy.count if snapshot else 0
        return {
            "count": count,
            "peak": snapshot.occupancy.peak if snapshot else 0,
            "capacity": monitor.capacity,
            "status": capacity_status(count, monitor.capacity).value,
            "running": app.state.worker.is_alive(),
            "ai": analyst.name if analyst else None,
        }

    @app.post("/api/capacity")
    def set_capacity(body: Capacity, request: Request) -> dict[str, int]:
        require_presenter(request)
        monitor.capacity = body.capacity
        return {"capacity": monitor.capacity}

    @app.get("/api/feed")
    def get_feed(after: int = 0, role: Role | None = None) -> list[dict[str, object]]:
        items = feed.since(after)
        if role is not None:  # a phone sees what happens in the room and its own team's decisions
            items = [
                item for item in items if item.kind in ROOM_WIDE or (item.kind == "decision" and item.role == role)
            ]
        return [asdict(item) for item in items]

    @app.post("/api/ask")
    def ask(body: Question, request: Request) -> dict[str, str]:
        if analyst is None:
            raise HTTPException(status_code=503, detail="La IA no está activada en este servidor.")
        snapshot = display.latest()
        if snapshot is None:
            raise HTTPException(status_code=503, detail="La cámara todavía no tiene imagen.")
        person = request.headers.get("cf-connecting-ip") or body.client_id or "anon"
        if not limits.allow(person):
            raise HTTPException(status_code=429, detail="Llegaste al límite de preguntas; espera un minuto.")
        if not limits.slots.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="La IA está respondiendo a otros; intenta en unos segundos.")
        try:
            answer = services.ask_about_the_room(
                analyst, snapshot.clean_jpeg(), body.question, body.role, snapshot.occupancy.count, monitor.capacity
            )
        except services.InvalidQuestion as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except AnalystError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error  # not 502: Cloudflare replaces those
        finally:
            limits.slots.release()
        feed.add("question", answer, body.role, question=" ".join(body.question.split()))
        return {"answer": answer}

    @app.post("/api/analyze")
    def analyze(request: Request) -> dict[str, str]:
        require_presenter(request)
        if analyst is None:
            raise HTTPException(status_code=503, detail="La IA no está activada en este servidor.")
        snapshot = display.latest()
        if snapshot is None:
            raise HTTPException(status_code=503, detail="La cámara todavía no tiene imagen.")
        with limits.slots:  # the presenter waits for a free slot instead of being turned away
            try:
                description = services.describe_the_room(
                    analyst, snapshot.clean_jpeg(), snapshot.occupancy.count, monitor.capacity
                )
            except AnalystError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
        feed.add("analysis", description)
        return {"description": description}

    @app.get("/api/qr.svg")
    def qr(request: Request) -> Response:
        url = f"{public_url or str(request.base_url).rstrip('/')}/m"
        svg = io.BytesIO()  # save() writes a standalone SVG; svg_inline() lacks the xmlns an <img> needs
        segno.make(url, error="m").save(svg, kind="svg", scale=8, border=2, dark="#0f1115", light="#ffffff")
        return Response(svg.getvalue(), media_type="image/svg+xml")

    @app.get("/api/public-url")
    def get_public_url(request: Request) -> dict[str, str]:
        return {"url": f"{public_url or str(request.base_url).rstrip('/')}/m"}

    @app.get("/video")
    def video(request: Request) -> StreamingResponse:
        require_presenter(request)  # the camera image never leaves the laptop through the tunnel
        return StreamingResponse(mjpeg_stream(display), media_type="multipart/x-mixed-replace; boundary=frame")

    return app


async def mjpeg_stream(display: WebDisplay, fps: int = 30) -> AsyncIterator[bytes]:
    """Motion JPEG: the browser replaces the image every time a new part arrives."""
    last_number = None
    while not display.closed:
        snapshot = display.latest()
        if snapshot and snapshot.number != last_number:
            last_number = snapshot.number
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + snapshot.jpeg + b"\r\n"
        await asyncio.sleep(1 / fps)


class Server(uvicorn.Server):
    """Closes the display as soon as Ctrl+C is pressed.

    That ends the video streams, so uvicorn doesn't wait for them until it times out.
    """

    def __init__(self, config: uvicorn.Config, display: WebDisplay):
        super().__init__(config)
        self._display = display

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        self._display.close()
        super().handle_exit(sig, frame)


def lan_ip() -> str:
    """This computer's address on the local network (no data is actually sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 80))
        ip: str = probe.getsockname()[0]
        return ip


def main() -> None:
    load_dotenv(find_dotenv(usecwd=True))  # ANTHROPIC_API_KEY from a .env here or in a parent folder
    parser = build_parser("Count the people in a room with YOLO, in the browser.")
    parser.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to open it from other devices")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--capacity", type=int, default=DEFAULT_CAPACITY, help="people allowed in the room")
    parser.add_argument("--tunnel", action="store_true", help="public URL + QR so phones can join from any network")
    parser.add_argument("--ai", choices=["claude", "gemini"], default="claude", help="who answers about the room")
    parser.add_argument("--claude-model", default=DEFAULT_CLAUDE_MODEL)
    parser.add_argument("--gemini-model", help=f"default: the first free of {', '.join(DEFAULT_GEMINI_MODELS)}")
    parser.add_argument("--no-ai", action="store_true", help="only count, don't call any AI")
    args = parser.parse_args()

    tunnel = CloudflareQuickTunnel(args.port) if args.tunnel else None
    public_url = None
    if tunnel:
        print("Opening the tunnel...")
        try:
            public_url = tunnel.start()
        except TunnelError as error:
            # Plan B: the demo goes on, and phones join through this Wi-Fi instead of the internet.
            print(f"{error}\nFalling back to the local network: phones must be on this same Wi-Fi.")
            tunnel = None
            args.host = "0.0.0.0"
    if public_url is None and args.host == "0.0.0.0":
        public_url = f"http://{lan_ip()}:{args.port}"

    analyst: SceneAnalyst | None = None
    if args.ai == "gemini" and not args.no_ai:
        analyst = GeminiSceneAnalyst((args.gemini_model,) if args.gemini_model else DEFAULT_GEMINI_MODELS)
    elif not args.no_ai:
        analyst = ClaudeSceneAnalyst(args.claude_model)
    if analyst:
        print(f"AI: {analyst.name}")
    app = create_app(bootstrap_from(args), analyst, args.capacity, public_url)
    print(f"Presenter screen: http://localhost:{args.port}")
    if public_url:
        print(f"Phones:           {public_url}/m")
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="warning")
    try:
        with suppress(KeyboardInterrupt):  # Ctrl+C is the normal way to stop, not an error
            Server(config, app.state.display).run()
    finally:
        if tunnel:
            tunnel.stop()
