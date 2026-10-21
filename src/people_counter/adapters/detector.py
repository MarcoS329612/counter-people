from typing import Protocol

import numpy as np
from ultralytics.engine.results import Results
from ultralytics.models import YOLO

from people_counter.domain.model import BoundingBox, Detection

PERSON_CLASS_ID = 0  # "person" in the COCO dataset the pretrained models were trained on


class PersonDetector(Protocol):
    def detect(self, frame: np.ndarray) -> list[Detection]: ...


class YoloPersonDetector:
    """Pretrained YOLO model. Returns every candidate, the domain decides which to count."""

    MIN_CANDIDATE_CONFIDENCE = 0.1

    def __init__(self, model_path: str = "yolo26n.pt", image_size: int = 640):
        self._model_path = model_path
        self._model = YOLO(model_path)
        self._image_size = image_size

    def detect(self, frame: np.ndarray) -> list[Detection]:
        (result,) = self._model.predict(  # one frame in, one result out
            frame,
            classes=[PERSON_CLASS_ID],
            conf=self.MIN_CANDIDATE_CONFIDENCE,
            imgsz=self._image_size,
            verbose=False,
        )
        boxes = result.boxes if isinstance(result, Results) else None
        if boxes is None:  # e.g. a classification model, which has no boxes
            raise ValueError(f"{self._model_path!r} doesn't detect objects; use a detection model like yolo26n.pt")
        return [
            Detection(BoundingBox(*xyxy), confidence)
            for xyxy, confidence in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), strict=True)
        ]
