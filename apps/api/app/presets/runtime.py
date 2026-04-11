"""Runtime contracts — Protocol definitions for pluggable training/prediction/conversion.

These protocols define the interfaces that concrete implementations must satisfy.
Presets reference implementations via importable ``module:function`` entrypoints;
the platform dynamically loads and validates them against these contracts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.presets.schema import PresetSpec


# ---------------------------------------------------------------------------
# Shared context objects passed to runtime entrypoints
# ---------------------------------------------------------------------------


@dataclass
class ModelRef:
    """Reference to a model for loading."""

    uri: str = ""
    framework: str = "pytorch"
    architecture: str = ""
    base_model: str = ""
    checkpoint: str | None = None
    num_classes: int | None = None
    format: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetRef:
    """Reference to a platform dataset for data loading."""

    dataset_id: str = ""
    sample_ids: list[str] | None = None
    label_space: list[str] = field(default_factory=list)
    storage_uri_prefix: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrainContext:
    """Everything a Trainer needs to execute a training run."""

    job_id: str
    preset: PresetSpec
    model_ref: ModelRef
    dataset_ref: DatasetRef
    output_dir: str = ""
    config_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictContext:
    """Everything a Predictor needs to execute inference."""

    job_id: str
    preset: PresetSpec
    model_ref: ModelRef
    dataset_ref: DatasetRef
    target: str = ""
    config_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConvertContext:
    """Everything a Converter needs to transform a model."""

    job_id: str
    preset: PresetSpec
    model_ref: ModelRef
    input_format: str = ""
    output_format: str = ""
    output_dir: str = ""
    config_overrides: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Result objects returned by runtime entrypoints
# ---------------------------------------------------------------------------


@dataclass
class TrainResult:
    """Output of a training run."""

    model_uri: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    artifact_uris: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictResult:
    """Output of a single prediction."""

    sample_id: str = ""
    label: str = ""
    confidence: float | None = None
    scores: dict[str, float] = field(default_factory=dict)
    raw_output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchPredictResult:
    """Output of batch prediction."""

    predictions: list[PredictResult] = field(default_factory=list)
    total: int = 0
    successful: int = 0
    failed: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConvertResult:
    """Output of a model conversion step."""

    output_uri: str = ""
    output_format: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocol definitions
# ---------------------------------------------------------------------------


@runtime_checkable
class Trainer(Protocol):
    """Protocol for training entrypoints.

    A Trainer receives a fully resolved TrainContext and returns a TrainResult.
    Implementations are referenced by ``preset.train.entrypoint``.
    """

    async def train(self, ctx: TrainContext) -> TrainResult: ...


@runtime_checkable
class Predictor(Protocol):
    """Protocol for prediction entrypoints.

    A Predictor receives a PredictContext and returns batch results.
    Implementations are referenced by ``preset.predict.entrypoint``
    or ``preset.predict.targets.<name>.entrypoint``.
    """

    async def load_model(self, model_ref: ModelRef) -> None: ...

    async def predict_batch(self, ctx: PredictContext, samples: list[Any]) -> BatchPredictResult: ...

    async def predict_single(self, ctx: PredictContext, sample: Any) -> PredictResult: ...

    async def unload_model(self) -> None: ...


@runtime_checkable
class DatasetAdapter(Protocol):
    """Protocol for dataset adapters.

    Adapters bridge platform dataset/sample storage to the format
    expected by Trainers and Predictors.
    """

    async def load(self, dataset_ref: DatasetRef) -> Any: ...

    async def iterate_batches(self, batch_size: int) -> Any: ...


@runtime_checkable
class Converter(Protocol):
    """Protocol for model conversion entrypoints.

    A Converter transforms a model from one format to another
    (e.g. PyTorch → ONNX, fp32 → int8).
    """

    async def convert(self, ctx: ConvertContext) -> ConvertResult: ...
