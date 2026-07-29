from app.runtime_compat.ml.demo.domain import (
    BatchPredictResult,
    DatasetRef,
    ModelRef,
    PredictContext,
    PredictResult,
    TrainContext,
    TrainResult,
)
from app.runtime_compat.ml.demo.protocols import ArtifactStorage, LlmClient

__all__ = [
    "ArtifactStorage",
    "BatchPredictResult",
    "DatasetRef",
    "LlmClient",
    "ModelRef",
    "PredictContext",
    "PredictResult",
    "TrainContext",
    "TrainResult",
]
