from collections.abc import Callable
from functools import partial

from people_counter.adapters.detector import YoloPersonDetector
from people_counter.adapters.display import Display
from people_counter.adapters.frame_source import OpenCVFrameSource
from people_counter.domain.model import DEFAULT_MIN_CONFIDENCE, Occupancy, OccupancyCounter
from people_counter.service_layer import services

type CountPeople = Callable[[Display], Occupancy | None]


def bootstrap(
    source: int | str = 0,
    model: str = "yolo26n.pt",
    image_size: int = 640,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    window: int = 15,
) -> CountPeople:
    """Composition root: builds the real adapters once, for any entrypoint.

    Returns count_people() with everything injected except the display,
    because each entrypoint shows the result in its own way.
    """
    return partial(
        services.count_people,
        OpenCVFrameSource(source),
        YoloPersonDetector(model, image_size),
        OccupancyCounter(min_confidence, window),
    )
