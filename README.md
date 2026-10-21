# People counter

Live demo that counts the people in a conference room with a webcam and a pretrained YOLO model.

## Run it

```bash
uv sync
uv run people-counter                          # webcam 0
uv run people-counter --source talk.mp4        # a video file
uv run people-counter --image-size 960         # finds people at the back, but slower
uv run people-counter-web                      # in the browser: http://localhost:8000
uv run people-counter-web --host 0.0.0.0       # also from phones on the same Wi-Fi (prints the address)
uv run people-counter-web --source C920 --tunnel --capacity 40   # the live demo (see below)
```

In the window, press `q` or `Esc` to stop. The web version takes the same options, plus `--host`, `--port`,
`--capacity`, `--tunnel`, `--claude-model` and `--no-ai`.

## The live demo

- `--source C920` finds the webcam by name (its number changes when you plug it in again) and opens it at 1080p.
- `--tunnel` opens a public https URL with [cloudflared](https://github.com/cloudflare/cloudflared) (no account
  needed; a new URL every time) and shows it as a QR code on the presenter screen.
- The **presenter screen** (`http://localhost:8000`, only from the laptop) shows the video, the count against the
  capacity, the QR code and a feed of what happens. The `−` / `+` buttons change the capacity live: lower it below
  the count to trigger the "over capacity" event on stage.
- The **phone page** (`/m`): each person picks a team (Seguridad, Operaciones, Dirección), gets that team's
  decision when the room goes over capacity, and asks Claude about what the camera sees.
- Claude needs `ANTHROPIC_API_KEY=sk-ant-...` in a `.env` file (in this folder or a parent one).
- Backup model: `--ai gemini` uses Gemini with the same prompts (`GEMINI_API_KEY=...` in `.env`). It tries
  several Gemini models in turn when one is saturated. On the free tier that happens often; turn on billing
  in the Google Cloud project for reliable answers.
- `./demo.sh` starts it all in the background (C920 if plugged in, tunnel, capacity 40); `./demo.sh stop` stops it.

Through the tunnel the camera image is never served (`/video` and the capacity buttons only work from the laptop),
and questions are rate-limited so a leaked link can't spend the API budget. Frames are sent to Claude only when
someone asks or the capacity is crossed, and nothing is saved.

## Tests

```bash
uv run pytest tests/unit          # domain + service layer, with fakes: milliseconds
uv run pytest tests/integration   # real adapters (YOLO, JPEG encoding): seconds, downloads weights once
uv run pytest tests/e2e           # the web app, with a fake camera and model
```

## Code quality

```bash
uv run ruff format   # format the code
uv run ruff check    # lint: unused imports, likely bugs, import order...
uv run mypy          # strict type check (tests are relaxed: fakes may skip annotations)
```

## Design (following *Designing Machine Learning Systems*, ch. 2)

| | |
|---|---|
| **Goal** | Show the audience, live, how many people are in the room. |
| **ML task** | Object detection, class `person` only. Count = detections above a confidence threshold. |
| **Baseline** | Pretrained `yolo26n` (COCO). No training: COCO already has a `person` class. |
| **Metric** | Absolute error between the shown count and a manual count. |
| **Constraints** | Runs on a laptop CPU in real time (~11 FPS with a 1080p camera and `--image-size 960`, on an i5-8365U). Claude only looks when asked, not every frame. |
| **Known failure modes** | Occlusion (people behind others or behind chairs), small people at the back, backlight from windows. |
| **Mitigations** | Median over the last N frames (no flicker); `--image-size` for small people; put the camera high, at the front. |
| **Privacy** | Frames are processed in memory and never saved. Tell the audience the camera is on. |

## Architecture (following *Architecture Patterns with Python*)

```
bootstrap.py                  composition root: builds the real adapters (ch. 13)
entrypoints/cli.py            OpenCV window
entrypoints/web.py            FastAPI: presenter screen, phone page, MJPEG stream, API
service_layer/services.py     count_people(), ask_about_the_room(), decide_for_each_team(): depend only on ports
domain/model.py               Detection, Occupancy, OccupancyCounter, CapacityMonitor, Role: pure Python
adapters/                     ports (Protocols) + implementations
  frame_source.py             FrameSource   -> OpenCVFrameSource (webcam, file, RTSP)
  detector.py                 PersonDetector -> YoloPersonDetector
  display.py                  Display       -> OpenCVWindow
  web_display.py                            -> WebDisplay (latest frame as JPEG)
  scene_analyst.py            SceneAnalyst  -> ClaudeSceneAnalyst (answers questions, decides per team)
  gemini_analyst.py                         -> GeminiSceneAnalyst (same prompts, backup model)
  tunnel.py                   CloudflareQuickTunnel (public URL for the phones)
```

The model is a detail at the edge: the counting rules are tested with fake detectors, and
swapping YOLO for another model means writing one new adapter. The web version proved it:
it needed a new entrypoint and a new `Display` adapter, and no change to the domain or the service.

## License

[AGPL-3.0](LICENSE). The person detector is [Ultralytics YOLO](https://www.ultralytics.com/license), which is AGPL-3.0,
so this project is too: if you run a modified version as a web service, you must offer its source code to its users
(the phone page links here). Using it in a closed-source product needs an Ultralytics Enterprise License, or swapping
the detector for one with a permissive license (it's a single adapter: `adapters/detector.py`).

Technology logos in `docs/fuente/logos` come from [Simple Icons](https://simpleicons.org) (CC0); the brands belong to
their owners.
