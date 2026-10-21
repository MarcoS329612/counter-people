import asyncio

import numpy as np

from people_counter.adapters.web_display import WebDisplay
from people_counter.domain.model import Occupancy
from people_counter.entrypoints.web import mjpeg_stream

JPEG_START = b"\xff\xd8"


def black_frame() -> np.ndarray:
    return np.zeros((48, 64, 3), np.uint8)


def test_nothing_to_show_before_the_first_frame():
    assert WebDisplay().latest() is None


def test_keeps_the_latest_frame_as_jpeg():
    display = WebDisplay()
    display.show(black_frame(), Occupancy((), count=1, peak=1))
    display.show(black_frame(), Occupancy((), count=2, peak=2))

    snapshot = display.latest()

    assert snapshot is not None
    assert snapshot.number == 1
    assert snapshot.jpeg.startswith(JPEG_START)
    assert snapshot.occupancy.count == 2


def test_asks_the_counting_loop_to_stop_once_closed():
    display = WebDisplay()
    assert display.show(black_frame(), Occupancy((), 0, 0))

    display.close()

    assert not display.show(black_frame(), Occupancy((), 0, 0))


def test_video_stream_sends_the_frame_as_a_jpeg_part():
    display = WebDisplay()
    display.show(black_frame(), Occupancy((), 0, 0))

    part = asyncio.run(anext(mjpeg_stream(display)))

    assert part.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + JPEG_START)
