from __future__ import annotations

from typing import Any

from app.runtime_compat.ml.demo.detection.predictor import (
    DetectionPredictor as _DetectionPredictor,
)


def _make_detection_predictor(**kwargs: Any) -> _DetectionPredictor:
    return _DetectionPredictor(**kwargs)


DetectionV1Predictor = _make_detection_predictor
