import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

FULL_HD = (1920, 1080)


class FrameSourceError(Exception):
    pass


class FrameSource(Protocol):
    def frames(self) -> Iterator[np.ndarray]: ...


def find_camera(name: str) -> int | None:
    """Index of the first webcam whose name contains `name` (e.g. "C920"). Linux only."""
    devices = sorted(Path("/sys/class/video4linux").glob("video*"), key=lambda d: int(d.name.removeprefix("video")))
    for device in devices:
        if name.lower() in (device / "name").read_text().lower():
            return int(device.name.removeprefix("video"))  # the first node is the image, the next one is metadata
    return None


class OpenCVFrameSource:
    """Reads frames from a webcam (an int, e.g. 0), a video file or an RTSP URL.

    Live sources (webcams, streams) always give the newest frame: when the model is
    slower than the camera, old frames are dropped instead of piling up as lag.
    """

    def __init__(self, source: int | str, resolution: tuple[int, int] = FULL_HD):
        self._source = source
        self._resolution = resolution

    @property
    def _is_live(self) -> bool:
        return isinstance(self._source, int) or "://" in self._source

    def frames(self) -> Iterator[np.ndarray]:
        capture = cv2.VideoCapture(self._source)
        if not capture.isOpened():
            raise FrameSourceError(f"Cannot open video source: {self._source!r}")
        if isinstance(self._source, int):
            # Without this OpenCV opens webcams at 640x480. MJPG is what allows 1080p at full speed over USB.
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._resolution[0])
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._resolution[1])
        try:
            yield from self._newest_frames(capture) if self._is_live else self._every_frame(capture)
        finally:
            capture.release()

    @staticmethod
    def _every_frame(capture: cv2.VideoCapture) -> Iterator[np.ndarray]:
        while True:
            ok, frame = capture.read()
            if not ok:
                return
            yield frame

    @staticmethod
    def _newest_frames(capture: cv2.VideoCapture) -> Iterator[np.ndarray]:
        newest: list[np.ndarray | None] = [None]
        new_frame = threading.Condition()
        stopped = threading.Event()

        def read() -> None:
            while not stopped.is_set():
                ok, frame = capture.read()
                with new_frame:
                    newest[0] = frame if ok else None
                    if not ok:
                        stopped.set()
                    new_frame.notify()

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            while True:
                with new_frame:
                    new_frame.wait_for(lambda: newest[0] is not None or stopped.is_set())
                    frame, newest[0] = newest[0], None
                if frame is None:
                    return
                yield frame
        finally:
            stopped.set()
            reader.join(timeout=1)
