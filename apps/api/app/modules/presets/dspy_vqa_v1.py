"""Preset: DSPy VQA (v1)

Single-file preset for VQA optimization via DSPy bootstrap fewshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.datasets.domain.entities.vqa import VqaDatasetAdapter
from app.modules.presets._registry import register
from app.modules.training.infrastructure.runtime.dspy import (
    DspyVqaPredictor,
    DspyVqaTrainer,
)


# ===== Typed config =====
@dataclass
class DspyVqaConfig:
    optimizer: str = "bootstrap_fewshot"
    max_demos: int = 8
    instruction: str = (
        "Answer the question using only image evidence. "
        "If uncertain, say you are unsure."
    )
    base_model: str = "gpt-4o-mini"

    @classmethod
    def defaults(cls) -> DspyVqaConfig:
        return cls()


# ===== Registration =====
@register(
    id="dspy-vqa-v1",
    name="DSPy VQA (v1)",
    version="1.0.0",
    description="VQA optimization preset for image + question → text answer.",
    tags=["dspy", "vqa", "multimodal"],
    trainable=True,
    dataset_types=["image_vqa"],
    task_types=["vqa"],
    prediction_targets=["vqa"],
    queue="optimize-llm-cpu",
    resources={"cpu": "2", "memory": "4Gi", "gpu": 0},
    model={
        "framework": "dspy",
        "architecture": "vqa-program",
        "base_model": "gpt-4o-mini",
    },
    team="llm-platform",
    maintainer="llm-platform@example.com",
)
class DspyVqaV1:
    """Preset entrypoint — all behaviour composed via static methods."""

    @staticmethod
    def train(
        *, artifact_storage: Any = None, llm_client: Any = None, **kwargs: Any
    ) -> Any:
        return DspyVqaTrainer(
            artifact_storage=artifact_storage,
            llm_client=llm_client,
        )

    @staticmethod
    def predict(
        target: str,
        *,
        model_uri: str = "",
        artifact_storage: Any = None,
        llm_client: Any = None,
        **kwargs: Any,
    ) -> Any:
        return DspyVqaPredictor(
            artifact_storage=artifact_storage,
            llm_client=llm_client,
        )

    @staticmethod
    def pipeline(ctx: Any = None):
        return VqaDatasetAdapter()
