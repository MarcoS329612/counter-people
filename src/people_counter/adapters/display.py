from collections.abc import Iterable
from typing import Protocol

import cv2
import numpy as np

from people_counter.domain.model import Detection, Occupancy

GREEN = (0, 200, 0)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
QUIT_KEYS = {ord("q"), 27}  # q or Esc


def draw_people(frame: np.ndarray, people: Iterable[Detection]) -> None:
    for person in people:
        top_left = (int(person.box.x1), int(person.box.y1))
        bottom_right = (int(person.box.x2), int(person.box.y2))
        cv2.rectangle(frame, top_left, bottom_right, GREEN, 2)


class Display(Protocol):
    def show(self, frame: np.ndarray, occupancy: Occupancy) -> bool:
        """Shows the frame. Returns False when the user wants to stop."""
        ...

    def close(self) -> None: ...


class OpenCVWindow:
    def __init__(self, title: str = "People counter"):
        self._title = title
        cv2.namedWindow(self._title, cv2.WINDOW_NORMAL)

    def show(self, frame: np.ndarray, occupancy: Occupancy) -> bool:
        draw_people(frame, occupancy.people)
        self._draw_label(frame, f"People in the room: {occupancy.count}", (20, 50), scale=1.4)
        self._draw_label(frame, f"Peak: {occupancy.peak}", (20, 100), scale=0.9)

        cv2.imshow(self._title, frame)
        key = cv2.waitKey(1) & 0xFF
        window_closed = cv2.getWindowProperty(self._title, cv2.WND_PROP_VISIBLE) < 1
        return key not in QUIT_KEYS and not window_closed

    def close(self) -> None:
        cv2.destroyAllWindows()

    @staticmethod
    def _draw_label(frame: np.ndarray, text: str, origin: tuple[int, int], scale: float) -> None:
        font = cv2.FONT_HERSHEY_SIMPLEX
        thickness = 2
        (width, height), baseline = cv2.getTextSize(text, font, scale, thickness)
        x, y = origin
        cv2.rectangle(frame, (x - 10, y - height - 10), (x + width + 10, y + baseline + 5), BLACK, -1)
        cv2.putText(frame, text, origin, font, scale, WHITE, thickness, cv2.LINE_AA)
