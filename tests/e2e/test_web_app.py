import threading
import time

import numpy as np
from fastapi.testclient import TestClient

from people_counter.domain.model import Occupancy, Role
from people_counter.entrypoints.web import create_app

PRESENTER = ("127.0.0.1", 50000)
THROUGH_TUNNEL = {"cf-connecting-ip": "203.0.113.7"}  # Cloudflare adds this to every request from the internet


def fake_count_people(occupancy: Occupancy, shown: threading.Event):
    """Stands in for the camera + model: shows one black frame and stops."""

    def count_people(display):
        display.show(np.zeros((48, 64, 3), np.uint8), occupancy)
        shown.set()
        return occupancy

    return count_people


class FakeAnalyst:
    name = "Fake"

    def answer(self, image_jpeg, question, role, count, capacity):
        return f"{role}: veo {count} personas"

    def decide(self, image_jpeg, event):
        return {role: f"Decisión para {role}" for role in Role}

    def describe(self, image_jpeg, count, capacity):
        return f"Veo {count} personas atentas."


def running_app(people: int = 3, peak: int = 5, capacity: int = 40):
    shown = threading.Event()
    app = create_app(fake_count_people(Occupancy((), people, peak), shown), FakeAnalyst(), capacity)
    return app, shown


def test_presenter_gets_the_big_screen():
    app, _ = running_app()
    with TestClient(app, client=PRESENTER) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Personas en la sala" in response.text


def test_phones_through_the_tunnel_go_to_the_phone_page():
    app, _ = running_app()
    with TestClient(app, client=PRESENTER) as client:
        response = client.get("/", headers=THROUGH_TUNNEL, follow_redirects=False)

    assert response.headers["location"] == "/m"


def test_the_camera_image_is_not_served_through_the_tunnel():
    app, _ = running_app()
    with TestClient(app, client=PRESENTER) as client:
        response = client.get("/video", headers=THROUGH_TUNNEL)

    assert response.status_code == 403


def test_reports_the_latest_occupancy_and_capacity():
    app, shown = running_app(people=4, peak=5, capacity=5)

    with TestClient(app) as client:
        assert shown.wait(timeout=2)
        data = client.get("/api/occupancy").json()

    assert (data["count"], data["peak"], data["capacity"], data["status"]) == (4, 5, 5, "near")


def test_only_the_presenter_changes_the_capacity():
    app, _ = running_app()
    with TestClient(app, client=PRESENTER) as client:
        from_phone = client.post("/api/capacity", json={"capacity": 1}, headers=THROUGH_TUNNEL)
        from_presenter = client.post("/api/capacity", json={"capacity": 25})

        assert from_phone.status_code == 403
        assert from_presenter.json() == {"capacity": 25}
        assert client.get("/api/occupancy").json()["capacity"] == 25


def test_answers_a_question_from_a_phone_and_shows_it_on_the_big_screen():
    app, shown = running_app(people=3)

    with TestClient(app) as client:
        assert shown.wait(timeout=2)
        response = client.post("/api/ask", json={"role": "safety", "question": "¿Cuántos hay?"})
        feed = client.get("/api/feed").json()

    assert response.json() == {"answer": "safety: veo 3 personas"}
    assert feed[-1]["kind"] == "question"
    assert feed[-1]["question"] == "¿Cuántos hay?"


def test_limits_how_many_questions_one_person_asks():
    app, shown = running_app()

    with TestClient(app) as client:
        assert shown.wait(timeout=2)
        statuses = [
            client.post("/api/ask", json={"role": "safety", "question": "¿Qué ves?", "client_id": "me"}).status_code
            for _ in range(6)
        ]

    assert statuses == [200] * 5 + [429]


def test_going_over_capacity_sends_each_team_its_decision():
    app, shown = running_app(people=3)

    with TestClient(app, client=PRESENTER) as client:
        assert shown.wait(timeout=2)
        client.post("/api/capacity", json={"capacity": 2})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not client.get("/api/feed?role=safety").json()[1:]:
            time.sleep(0.1)
        for_safety = client.get("/api/feed?role=safety").json()

    assert [item["kind"] for item in for_safety] == ["event", "decision"]
    assert for_safety[1]["text"] == "Decisión para safety"


def test_qr_code_is_a_standalone_svg_pointing_to_the_phone_page():
    shown = threading.Event()
    app = create_app(fake_count_people(Occupancy((), 0, 0), shown), public_url="https://demo.example")

    with TestClient(app) as client:
        svg = client.get("/api/qr.svg")
        url = client.get("/api/public-url").json()["url"]

    assert svg.headers["content-type"] == "image/svg+xml"
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg.text  # without it browsers don't draw it in an <img>
    assert url == "https://demo.example/m"


def test_the_presenter_asks_claude_to_describe_the_room_and_phones_see_it():
    app, shown = running_app(people=3)

    with TestClient(app, client=PRESENTER) as client:
        assert shown.wait(timeout=2)
        from_phone = client.post("/api/analyze", headers=THROUGH_TUNNEL)
        from_presenter = client.post("/api/analyze")
        on_a_phone = client.get("/api/feed?role=operations").json()

    assert from_phone.status_code == 403
    assert from_presenter.json() == {"description": "Veo 3 personas atentas."}
    assert [(item["kind"], item["text"]) for item in on_a_phone] == [("analysis", "Veo 3 personas atentas.")]
