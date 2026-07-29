from __future__ import annotations

from typing import Any

from app.runtime_compat.ml.demo.vqa import VqaPredictor as _VqaPredictor


def _make_dspy_vqa_predictor(**kwargs: Any) -> _VqaPredictor:
    return _VqaPredictor(**kwargs)


DspyVqaPredictor = _make_dspy_vqa_predictor
