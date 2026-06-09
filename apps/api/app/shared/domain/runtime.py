"""Compatibility shim for shared runtime contracts.

The canonical definitions live in :mod:`platform_runtime.contracts`.  Keep this
module as a stable API import path until downstream API imports are migrated.
"""

from __future__ import annotations

from importlib import import_module

_contracts = import_module("platform_runtime.contracts")

BatchPredictResult = _contracts.BatchPredictResult
DatasetAdapter = _contracts.DatasetAdapter
DatasetRef = _contracts.DatasetRef
JobRef = _contracts.JobRef
ModelRef = _contracts.ModelRef
PredictContext = _contracts.PredictContext
PredictResult = _contracts.PredictResult
Predictor = _contracts.Predictor
StorageDescriptor = _contracts.StorageDescriptor
TrainContext = _contracts.TrainContext
TrainResult = _contracts.TrainResult
Trainer = _contracts.Trainer

__all__ = [
    "BatchPredictResult",
    "DatasetAdapter",
    "DatasetRef",
    "JobRef",
    "ModelRef",
    "PredictContext",
    "PredictResult",
    "Predictor",
    "StorageDescriptor",
    "TrainContext",
    "TrainResult",
    "Trainer",
]
