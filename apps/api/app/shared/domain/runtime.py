"""API-local runtime contracts for in-process trainers and predictors.

These are internal Python contracts. External SDK/runtime boundaries should use OpenAPI, protobuf, or other generated transport contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class JobRef:
    """Reference to a platform job or external runtime job."""

    job_id: str = ""
    external_job_id: str | None = None
    kind: str = ""
    status: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StorageDescriptor:
    """Descriptor for data or artifact storage used by runtime tasks."""

    uri: str = ""
    kind: str = ""
    format: str | None = None
    credentials_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


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
    job_id: str
    trainer_id: str = ""
    train_config: dict[str, Any] = field(default_factory=dict)
    model_ref: ModelRef = field(default_factory=ModelRef)
    dataset_ref: DatasetRef = field(default_factory=DatasetRef)
    view_type: str = ""
    view_options: dict[str, Any] = field(default_factory=dict)
    output_dir: str = ""
    config_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictContext:
    job_id: str
    trainer_id: str = ""
    predict_config: dict[str, Any] = field(default_factory=dict)
    model_ref: ModelRef = field(default_factory=ModelRef)
    dataset_ref: DatasetRef = field(default_factory=DatasetRef)
    target: str = ""
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


class ArtifactStorage(Protocol):
    """Storage backend for runtime artifacts."""

    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Store bytes and return the URI."""
        ...

    async def get_bytes(self, uri: str) -> bytes:
        """Retrieve bytes from the given URI."""
        ...

    async def delete(self, uri: str) -> None:
        """Delete the object at the given URI."""
        ...

    async def list_prefix(self, prefix: str) -> list[str]:
        """Return URIs of all objects whose key starts with the given prefix."""
        ...


class LlmClient(Protocol):
    """Multimodal LLM client for VQA generation."""

    async def answer_vqa(
        self,
        *,
        image_bytes: bytes,
        question: str,
        system_prompt: str,
    ) -> str:
        """Generate an answer for a visual question."""
        ...


class EmbeddingClient(Protocol):
    """Client for generating image embeddings."""

    async def embed_image(
        self,
        image_bytes: bytes,
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> list[float]: ...

    async def classify_image(
        self,
        image_bytes: bytes,
        labels: list[str],
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> tuple[str, float, dict[str, float]]: ...

    async def classify_batch(
        self,
        images: list[bytes],
        labels: list[str],
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> list[tuple[str, float, dict[str, float]]]: ...

    async def health(self) -> bool: ...


__all__ = [
    "ArtifactStorage",
    "BatchPredictResult",
    "DatasetAdapter",
    "DatasetRef",
    "EmbeddingClient",
    "JobRef",
    "LlmClient",
    "ModelRef",
    "PredictContext",
    "PredictResult",
    "Predictor",
    "StorageDescriptor",
    "TrainContext",
    "TrainResult",
    "Trainer",
]
