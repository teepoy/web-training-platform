from __future__ import annotations

from typing import Any

from app.runtime_compat.ml.demo.classification.predictor import (
    ClassificationPredictor as _ClassificationPredictor,
)


def _make_resnet_predictor(**kwargs: Any) -> _ClassificationPredictor:
    return _ClassificationPredictor(**kwargs)


ResnetPredictor = _make_resnet_predictor
