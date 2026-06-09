from __future__ import annotations

from typing import Any

from app.core.registry import predictor
from libs.ml.classification.predictor import (
    ClassificationPredictor as _ClassificationPredictor,
)


def _make_resnet_predictor(**kwargs: Any) -> _ClassificationPredictor:
    return _ClassificationPredictor(**kwargs)


ResnetPredictor = predictor(
    id="resnet50-cls-v1", name="ResNet-50 Classification", view_id="image_input_v1"
)(_make_resnet_predictor)
