from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from statistics import median_low

DEFAULT_MIN_CONFIDENCE = 0.7  # high: prefer missing someone over counting a coat as a person
NEAR_CAPACITY = 0.8  # from 80% of the capacity the room is "almost full"


@dataclass(frozen=True)
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class Detection:
    box: BoundingBox
    confidence: float


@dataclass(frozen=True)
class Occupancy:
    people: tuple[Detection, ...]  # people detected in the current frame
    count: int  # smoothed number of people in the room
    peak: int  # highest count seen so far


class OccupancyCounter:
    """Counts the people in the room.

    Detectors miss people for a frame or two (occlusion, motion blur), so the
    reported count is the median of the last `window` frames. That way the
    number on screen doesn't flicker.
    """

    def __init__(self, min_confidence: float = DEFAULT_MIN_CONFIDENCE, window: int = 15):
        if window < 1:
            raise ValueError("window must be at least 1 frame")
        self.min_confidence = min_confidence
        self._recent_counts: deque[int] = deque(maxlen=window)
        self._peak = 0

    def update(self, detections: Iterable[Detection]) -> Occupancy:
        people = tuple(d for d in detections if d.confidence >= self.min_confidence)
        self._recent_counts.append(len(people))
        count = median_low(self._recent_counts)
        self._peak = max(self._peak, count)
        return Occupancy(people=people, count=count, peak=self._peak)


class Role(StrEnum):
    """The teams that act when something happens in the room."""

    SAFETY = "safety"
    OPERATIONS = "operations"
    MANAGEMENT = "management"


class CapacityStatus(StrEnum):
    OK = "ok"
    NEAR = "near"
    FULL = "full"
    OVER = "over"


def capacity_status(count: int, capacity: int) -> CapacityStatus:
    if count > capacity:
        return CapacityStatus.OVER
    if count == capacity:
        return CapacityStatus.FULL
    if count >= capacity * NEAR_CAPACITY:
        return CapacityStatus.NEAR
    return CapacityStatus.OK


@dataclass(frozen=True)
class CapacityEvent:
    exceeded: bool  # True when the room goes over capacity, False when it is back under it
    count: int
    capacity: int


class CapacityMonitor:
    """Turns the smoothed count into events: only the moments the room crosses its capacity."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._over = False

    def check(self, count: int) -> CapacityEvent | None:
        over = count > self.capacity
        if over == self._over:
            return None
        self._over = over
        return CapacityEvent(exceeded=over, count=count, capacity=self.capacity)
