"""Runs the real model, so it is slow and downloads the weights on the first run."""

import cv2
from ultralytics.utils import ASSETS

from people_counter.adapters.detector import YoloPersonDetector


def test_finds_the_people_in_the_bus_picture():
    frame = cv2.imread(str(ASSETS / "bus.jpg"))  # a sample image with 4 people (confidences 0.66 to 0.87)
    assert frame is not None

    detections = YoloPersonDetector().detect(frame)

    # This tests the adapter only; which confidence counts as a person is the domain's decision.
    assert len([d for d in detections if d.confidence >= 0.5]) == 4
