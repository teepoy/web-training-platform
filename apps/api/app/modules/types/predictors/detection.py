from __future__ import annotations

from typing import Any

from app.core.registry import predictor
from libs.ml.detection.predictor import DetectionPredictor as _DetectionPredictor


def _make_detection_predictor(**kwargs: Any) -> _DetectionPredictor:
    return _DetectionPredictor(**kwargs)


DetectionV1Predictor = predictor(
    id="detection-v1", name="Detection V1", view_id="box_detection_v1"
)(_make_detection_predictor)
