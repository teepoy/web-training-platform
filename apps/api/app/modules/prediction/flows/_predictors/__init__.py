"""Flow-runtime predictor loading for prediction flows.

Prediction modules register with the central executable registry. This module
keeps the flow-facing lazy loader and returns the raw callable expected by
``predict_job.py``.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from app.core.registry import get_predictor as get_registered_predictor
from app.core.registry import predictor as predictor

_PREDICTOR_MODULES: dict[str, str] = {
    "resnet50-sc-v1": "app.modules.prediction.flows._predictors.sc",
    "yolo-sc-v1": "app.modules.prediction.flows._predictors.yolo_sc",
}


def get_predictor(
    predictor_id: str,
) -> Callable[..., Any]:
    """Return an **executable** predictor callable by ID.

    Lazy-imports the predictor module on first call to trigger central
    ``@predictor`` registration. Only executable predictors are returned;
    metadata-only catalog entries are not considered.

    Raises:
        KeyError: No executable predictor registered for *predictor_id*.
    """
    module_name = _PREDICTOR_MODULES.get(predictor_id)
    if module_name is None:
        raise KeyError(
            f"predictor_id={predictor_id!r} not found in executable predictor registry"
        )
    importlib.import_module(module_name)
    try:
        registered = get_registered_predictor(predictor_id)
    except KeyError as exc:
        raise KeyError(
            f"predictor_id={predictor_id!r} not found in executable predictor registry"
        ) from exc
    return registered.func  # pyright: ignore[reportReturnType]
