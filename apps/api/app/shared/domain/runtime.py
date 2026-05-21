"""Shared runtime contracts for dataset, training, and prediction adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.modules.presets.schema import PresetSpec


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
    """Everything a trainer needs to execute a training run."""

    job_id: str
    preset: PresetSpec
    model_ref: ModelRef
    dataset_ref: DatasetRef
    output_dir: str = ""
    config_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictContext:
    """Everything a predictor needs to execute inference."""

    job_id: str
    preset: PresetSpec
    model_ref: ModelRef
    dataset_ref: DatasetRef
    target: str = ""
    config_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConvertContext:
    """Everything a converter needs to transform a model."""

    job_id: str
    preset: PresetSpec
    model_ref: ModelRef
    input_format: str = ""
    output_format: str = ""
    output_dir: str = ""
    config_overrides: dict[str, Any] = field(default_factory=dict)


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


@runtime_checkable
class Trainer(Protocol):
    """Protocol for training entrypoints."""

    async def train(self, ctx: TrainContext) -> TrainResult: ...


@runtime_checkable
class Predictor(Protocol):
    """Protocol for prediction entrypoints."""

    async def load_model(self, model_ref: ModelRef) -> None: ...

    async def predict_batch(
        self, ctx: PredictContext, samples: list[Any]
    ) -> BatchPredictResult: ...

    async def predict_single(
        self, ctx: PredictContext, sample: Any
    ) -> PredictResult: ...

    async def unload_model(self) -> None: ...


@runtime_checkable
class DatasetAdapter(Protocol):
    """Protocol for dataset adapters."""

    async def load(self, dataset_ref: DatasetRef) -> Any: ...

    async def iterate_batches(self, batch_size: int) -> Any: ...


@runtime_checkable
class Converter(Protocol):
    """Protocol for model conversion entrypoints."""

    async def convert(self, ctx: ConvertContext) -> ConvertResult: ...
