"""Compatibility shim for ML runtime domain types.

The canonical definitions live in :mod:`platform_runtime.contracts`.  This
module preserves the historical ``libs.ml.domain`` import path while runtime
boundary migration proceeds.
"""

from __future__ import annotations

from importlib import import_module

_contracts = import_module("platform_runtime.contracts")

BatchPredictResult = _contracts.BatchPredictResult
DatasetRef = _contracts.DatasetRef
ModelRef = _contracts.ModelRef
PredictContext = _contracts.PredictContext
PredictResult = _contracts.PredictResult
TrainContext = _contracts.TrainContext
TrainResult = _contracts.TrainResult


__all__ = [
    "BatchPredictResult",
    "DatasetRef",
    "ModelRef",
    "PredictContext",
    "PredictResult",
    "TrainContext",
    "TrainResult",
]
