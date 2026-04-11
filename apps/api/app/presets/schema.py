"""Preset schema — Pydantic models for engineer-managed preset YAML files.

A preset is the complete executable specification for a training/prediction
pipeline.  Engineers author ``preset.yaml`` files; the platform loads them
at startup and exposes a read-only catalog to users.

Required sections: model, train, predict.
Optional sections: test, convert, runtime, io.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Model section
# ---------------------------------------------------------------------------


class ModelSource(BaseModel):
    """Where the base model comes from."""

    framework: str = "pytorch"
    architecture: str
    base_model: str = Field(
        description="HuggingFace ID, torchvision name, or artifact URI",
    )
    checkpoint: str | None = Field(
        default=None,
        description="Optional checkpoint URI (s3://, memory://, local path)",
    )
    num_classes: int | None = None
    input: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Train section
# ---------------------------------------------------------------------------


class DataloaderSpec(BaseModel):
    ref: str = Field(description="Importable module:function reference")
    params: dict[str, Any] = Field(default_factory=dict)


class TrainConfig(BaseModel):
    entrypoint: str = Field(description="Importable module:function for training")
    config: dict[str, Any] = Field(default_factory=dict)
    dataloader: DataloaderSpec | None = None


# ---------------------------------------------------------------------------
# Predict section — supports multiple prediction targets
# ---------------------------------------------------------------------------


class PredictTarget(BaseModel):
    """A single prediction target (e.g. classification, detection, embedding)."""

    entrypoint: str = Field(description="Importable module:function for inference")
    config: dict[str, Any] = Field(default_factory=dict)
    dataloader: DataloaderSpec | None = None


class PredictConfig(BaseModel):
    """Prediction configuration — one default target, optionally many named targets."""

    entrypoint: str = Field(
        default="",
        description="Default prediction entrypoint (shorthand when single target)",
    )
    config: dict[str, Any] = Field(default_factory=dict)
    dataloader: DataloaderSpec | None = None
    targets: dict[str, PredictTarget] = Field(
        default_factory=dict,
        description="Named prediction targets (classification, detection, embedding, ...)",
    )


# ---------------------------------------------------------------------------
# Test / Evaluate section (optional)
# ---------------------------------------------------------------------------


class TestConfig(BaseModel):
    enabled: bool = True
    entrypoint: str = Field(description="Importable module:function for evaluation")
    metrics: list[str] = Field(default_factory=list)
    dataloader: DataloaderSpec | None = None


# ---------------------------------------------------------------------------
# Conversion / quantization section (optional)
# ---------------------------------------------------------------------------


class ConvertStep(BaseModel):
    """A single model conversion step (e.g. pytorch -> onnx)."""

    name: str
    entrypoint: str = Field(description="Importable module:function for conversion")
    input_format: str
    output_format: str
    config: dict[str, Any] = Field(default_factory=dict)


class ConvertConfig(BaseModel):
    steps: list[ConvertStep] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Runtime section (optional)
# ---------------------------------------------------------------------------


class RuntimeResources(BaseModel):
    cpu: str = "2"
    memory: str = "4Gi"
    gpu: int = 0


class RuntimeConfig(BaseModel):
    environment: str = "dev"
    device: str = "auto"
    image: str | None = None
    queue: str | None = Field(
        default=None,
        description="Prefect work queue name for routing",
    )
    resources: RuntimeResources = Field(default_factory=RuntimeResources)
    retry: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# IO / Dataset adapter section (optional)
# ---------------------------------------------------------------------------


class IOConfig(BaseModel):
    """Dataset adapter specification."""

    adapter: str = Field(
        default="",
        description="Importable module:function that builds a dataset adapter",
    )
    expected_sample_schema: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Compatibility section (optional)
# ---------------------------------------------------------------------------


class CompatConfig(BaseModel):
    min_api_version: str | None = None
    max_api_version: str | None = None


class PresetCompatibility(BaseModel):
    dataset_types: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)
    prediction_targets: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Ownership metadata (optional)
# ---------------------------------------------------------------------------


class OwnershipConfig(BaseModel):
    team: str = ""
    maintainer: str = ""


# ---------------------------------------------------------------------------
# Top-level Preset model
# ---------------------------------------------------------------------------


class PresetSpec(BaseModel):
    """Complete preset specification loaded from a preset.yaml file."""

    id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    deprecated: bool = False
    trainable: bool = True

    model: ModelSource
    train: TrainConfig
    predict: PredictConfig
    test: TestConfig | None = None
    convert: ConvertConfig | None = None
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    io: IOConfig = Field(default_factory=IOConfig)
    compat: CompatConfig = Field(default_factory=CompatConfig)
    compatibility: PresetCompatibility = Field(default_factory=PresetCompatibility)
    ownership: OwnershipConfig = Field(default_factory=OwnershipConfig)
