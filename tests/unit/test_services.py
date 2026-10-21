import pytest

from people_counter.domain.model import BoundingBox, CapacityEvent, Detection, Occupancy, OccupancyCounter, Role
from people_counter.service_layer import services


def person() -> Detection:
    return Detection(BoundingBox(0, 0, 10, 20), confidence=0.9)


class FakeFrameSource:
    def __init__(self, frames):
        self._frames = frames

    def frames(self):
        yield from self._frames


class FakeDetector:
    """Frames are just names; each one maps to the people "seen" in it."""

    def __init__(self, people_per_frame: dict[str, int]):
        self._people_per_frame = people_per_frame

    def detect(self, frame):
        return [person()] * self._people_per_frame[frame]


class FakeDisplay:
    def __init__(self, stop_after: int | None = None):
        self.shown: list[tuple[str, Occupancy]] = []
        self._stop_after = stop_after

    def show(self, frame, occupancy):
        self.shown.append((frame, occupancy))
        return self._stop_after is None or len(self.shown) < self._stop_after

    def close(self):
        pass


def test_shows_every_frame_with_its_count():
    display = FakeDisplay()

    services.count_people(
        FakeFrameSource(["f1", "f2"]),
        FakeDetector({"f1": 2, "f2": 3}),
        OccupancyCounter(window=1),
        display,
    )

    assert [(frame, o.count) for frame, o in display.shown] == [("f1", 2), ("f2", 3)]


def test_returns_the_last_occupancy():
    occupancy = services.count_people(
        FakeFrameSource(["f1", "f2"]),
        FakeDetector({"f1": 5, "f2": 1}),
        OccupancyCounter(window=1),
        FakeDisplay(),
    )

    assert occupancy is not None
    assert (occupancy.count, occupancy.peak) == (1, 5)


def test_stops_when_the_user_quits():
    display = FakeDisplay(stop_after=1)

    services.count_people(
        FakeFrameSource(["f1", "f2", "f3"]),
        FakeDetector({"f1": 1, "f2": 1, "f3": 1}),
        OccupancyCounter(),
        display,
    )

    assert len(display.shown) == 1


def test_empty_video_returns_none():
    occupancy = services.count_people(FakeFrameSource([]), FakeDetector({}), OccupancyCounter(), FakeDisplay())

    assert occupancy is None


class FakeAnalyst:
    name = "Fake"

    def __init__(self):
        self.questions = []

    def answer(self, image_jpeg, question, role, count, capacity):
        self.questions.append((question, role, count, capacity))
        return "Nadie trae chaleco."

    def decide(self, image_jpeg, event):
        return {role: f"{role} decide" for role in Role}

    def describe(self, image_jpeg, count, capacity):
        return f"{count} de {capacity}"


def test_asks_the_analyst_about_the_room():
    analyst = FakeAnalyst()

    answer = services.ask_about_the_room(
        analyst, b"jpeg", "  ¿Alguien trae   chaleco? ", Role.SAFETY, count=12, capacity=40
    )

    assert answer == "Nadie trae chaleco."
    assert analyst.questions == [("¿Alguien trae chaleco?", Role.SAFETY, 12, 40)]


@pytest.mark.parametrize("question", ["", "   ", "x" * (services.MAX_QUESTION_LENGTH + 1)])
def test_rejects_empty_or_huge_questions(question):
    analyst = FakeAnalyst()

    with pytest.raises(services.InvalidQuestion):
        services.ask_about_the_room(analyst, b"jpeg", question, Role.SAFETY, count=1, capacity=40)

    assert analyst.questions == []


def test_each_team_gets_its_own_decision():
    event = CapacityEvent(exceeded=True, count=42, capacity=40)

    decisions = services.decide_for_each_team(FakeAnalyst(), b"jpeg", event)

    assert set(decisions) == set(Role)


def test_describes_the_room_with_the_count():
    assert services.describe_the_room(FakeAnalyst(), b"jpeg", count=12, capacity=40) == "12 de 40"
