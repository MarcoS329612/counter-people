from typing import TYPE_CHECKING

from people_counter.domain.model import CapacityEvent, Occupancy, OccupancyCounter, Role

if TYPE_CHECKING:  # the ports are only type hints here, so tests don't load YOLO or OpenCV
    from people_counter.adapters.detector import PersonDetector
    from people_counter.adapters.display import Display
    from people_counter.adapters.frame_source import FrameSource
    from people_counter.adapters.scene_analyst import SceneAnalyst

MAX_QUESTION_LENGTH = 300


class InvalidQuestion(Exception):
    pass


def count_people(
    source: FrameSource,
    detector: PersonDetector,
    counter: OccupancyCounter,
    display: Display,
) -> Occupancy | None:
    """Counts people frame by frame until the video ends or the user stops.

    Returns the last occupancy, or None if the source had no frames.
    """
    occupancy = None
    for frame in source.frames():
        occupancy = counter.update(detector.detect(frame))
        if not display.show(frame, occupancy):
            break
    return occupancy


def ask_about_the_room(
    analyst: SceneAnalyst, image_jpeg: bytes, question: str, role: Role, count: int, capacity: int
) -> str:
    """Someone in the audience asks the AI about what the camera sees right now."""
    question = " ".join(question.split())
    if not question:
        raise InvalidQuestion("Escribe una pregunta.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise InvalidQuestion(f"La pregunta es muy larga (máximo {MAX_QUESTION_LENGTH} caracteres).")
    return analyst.answer(image_jpeg, question, role, count, capacity)


def decide_for_each_team(analyst: SceneAnalyst, image_jpeg: bytes, event: CapacityEvent) -> dict[Role, str]:
    """Orchestration: one event in the room, a different decision for each team."""
    return analyst.decide(image_jpeg, event)


def describe_the_room(analyst: SceneAnalyst, image_jpeg: bytes, count: int, capacity: int) -> str:
    """The presenter asks the AI to describe the room on the big screen."""
    return analyst.describe(image_jpeg, count, capacity)
