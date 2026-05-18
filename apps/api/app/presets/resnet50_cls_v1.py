"""Preset: ResNet50 Classification (v1)

Single-file preset — imports trainer, predictor, and pipeline from their
respective modules and composes them here.  All config is typed Python,
no YAML.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.presets._registry import register


# ===== Typed config =====
@dataclass
class Resnet50ClsConfig:
    optimizer: str = "adamw"
    learning_rate: float = 0.0003
    weight_decay: float = 0.01
    scheduler: str = "cosine"
    max_epochs: int = 30
    early_stopping_patience: int = 5
    mixed_precision: str = "fp16"
    batch_size: int = 64
    num_workers: int = 4
    top_k: int = 5
    score_threshold: float = 0.2
    output_dim: int = 2048

    @classmethod
    def defaults(cls) -> Resnet50ClsConfig:
        return cls()


# ===== Registration =====
@register(
    id="resnet50-cls-v1",
    name="ResNet50 Classification (v1)",
    version="1.0.0",
    description="Standard image classification preset using torchvision ResNet50.",
    tags=["classification", "resnet", "baseline"],
    trainable=True,
    dataset_types=["image_classification"],
    task_types=["classification"],
    prediction_targets=["image_classification", "embedding"],
    queue="train-gpu",
    resources={"cpu": "4", "memory": "8Gi", "gpu": 0},
    model={
        "framework": "pytorch",
        "architecture": "resnet50",
        "base_model": "torchvision/resnet50",
        "num_classes": 1000,
        "input": {"image_size": 224, "normalization": "imagenet"},
    },
    team="ml-platform",
    maintainer="ml-platform@example.com",
)
class Resnet50ClsV1:
    """Preset entrypoint — all behaviour composed via static methods."""

    @staticmethod
    def train(*, artifact_storage, **kwargs) -> Any:
        from app.runtime.torch import TorchTrainer

        return TorchTrainer(artifact_storage=artifact_storage)

    @staticmethod
    def predict(target: str, *, model_uri: str, artifact_storage, **kwargs) -> Any:
        from app.runtime.torch import TorchPredictor

        predictor = TorchPredictor(artifact_storage=artifact_storage)
        # Return predictor instance — caller handles load/predict/unload lifecycle
        return predictor

    @staticmethod
    def pipeline(ctx: Any = None) -> Any:
        from app.data.classification import ImageClassificationAdapter

        return ImageClassificationAdapter()
