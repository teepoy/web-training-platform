"""Preset: CLIP Zero-Shot Classification (v1)

Inference-only preset — trainable=False.
Uses OpenAI CLIP ViT-B/32 for zero-shot classification and embedding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.presets._registry import register


# ===== Typed config =====
@dataclass
class ClipZeroShotConfig:
    prompt_template: str = "a photo of a {}"
    top_k: int = 5
    score_threshold: float = 0.2
    output_dim: int = 2048

    @classmethod
    def defaults(cls) -> ClipZeroShotConfig:
        return cls()


# ===== Registration =====
@register(
    id="clip-zero-shot-v1",
    name="CLIP Zero-Shot Classification (v1)",
    version="1.0.0",
    description="Zero-shot classification using OpenAI CLIP ViT-B/32 via gRPC embedding service.",
    tags=["clip", "zero-shot", "classification"],
    trainable=False,
    dataset_types=["image_classification"],
    task_types=["classification"],
    prediction_targets=["image_classification", "embedding"],
    queue="predict-gpu",
    resources={"cpu": "2", "memory": "4Gi", "gpu": 0},
    model={
        "framework": "pytorch",
        "architecture": "clip-vit-b32",
        "base_model": "openai/clip-vit-base-patch32",
    },
    team="ml-platform",
    maintainer="ml-platform@example.com",
)
class ClipZeroShotV1:
    """Inference-only preset — no train() method."""

    @staticmethod
    def predict(target: str, *, model_uri: str, artifact_storage, **kwargs) -> Any:
        from app.modules.training.infrastructure.runtime.torch import TorchPredictor

        return TorchPredictor(artifact_storage=artifact_storage)

    @staticmethod
    def pipeline(ctx: Any = None) -> Any:
        from app.data.classification import ImageClassificationAdapter

        return ImageClassificationAdapter()
