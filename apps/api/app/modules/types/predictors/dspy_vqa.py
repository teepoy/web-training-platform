from __future__ import annotations

from typing import Any

from app.core.registry import predictor
from libs.ml.vqa import VqaPredictor as _VqaPredictor


def _make_dspy_vqa_predictor(**kwargs: Any) -> _VqaPredictor:
    return _VqaPredictor(**kwargs)


DspyVqaPredictor = predictor(id="dspy-vqa-v1", name="DSPy VQA", view_id="qa_input_v1")(
    _make_dspy_vqa_predictor
)
