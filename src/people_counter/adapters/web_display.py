import threading
from dataclasses import dataclass

import cv2
import numpy as np

from people_counter.adapters.display import draw_people
from people_counter.domain.model import Occupancy


@dataclass(frozen=True, eq=False)  # numpy arrays cannot be compared with ==
class Snapshot:
    number: int  # increases with every frame, so readers know when there is a new one
    jpeg: bytes  # with a box around each person, for the video stream
    occupancy: Occupancy
    frame: np.ndarray  # the frame as the camera saw it, without boxes, for the AI to look at

    def clean_jpeg(self, max_side: int = 1568) -> bytes:
        """The frame without boxes, no bigger than what Claude uses anyway (so it uploads faster)."""
        height, width = self.frame.shape[:2]
        scale = min(1.0, max_side / max(height, width))
        frame = (
            cv2.resize(self.frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else self.frame
        )
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpeg.tobytes()


class WebDisplay:
    """Keeps the latest annotated frame so web requests can read it.

    show() runs in the counting thread; latest() is called by the web server.
    """

    def __init__(self, jpeg_quality: int = 80):
        self._jpeg_quality = jpeg_quality
        self._lock = threading.Lock()
        self._latest: Snapshot | None = None
        self._closed = threading.Event()

    def show(self, frame: np.ndarray, occupancy: Occupancy) -> bool:
        clean = frame.copy()
        draw_people(frame, occupancy.people)
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality])
        with self._lock:
            number = self._latest.number + 1 if self._latest else 0
            self._latest = Snapshot(number, jpeg.tobytes(), occupancy, clean)
        return not self.closed

    def latest(self) -> Snapshot | None:
        with self._lock:
            return self._latest

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def close(self) -> None:
        self._closed.set()
