from __future__ import annotations
# pyright: reportMissingImports=false

import json
import math
import logging
from io import BytesIO
from typing import TYPE_CHECKING, Any

from PIL import Image
from prefect import get_run_logger

from app.shared.domain.runtime import (
    BatchPredictResult,
    PredictContext,
    PredictResult,
    TrainContext,
    TrainResult,
)

if TYPE_CHECKING:
    pass
from app.shared.domain.protocols import ArtifactStorage


def _image_embedding_from_bytes(image_bytes: bytes, dim: int = 64) -> list[float]:
    with Image.open(BytesIO(image_bytes)) as img:
        gray = img.convert("L").resize((8, 8))
        pixels = list(gray.tobytes())
    vals = [float(p) / 255.0 for p in pixels]
    if len(vals) < dim:
        vals.extend([0.0] * (dim - len(vals)))
    vec = vals[:dim]
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _logger():
    try:
        return get_run_logger()
    except Exception:
        return logging.getLogger(__name__)


# TODO(issue BLOCK-001): Deprecated — TorchPredictor is legacy,
# superseded by flow-level @predictor decorators in flows/_predictors/.
class TorchPredictor:
    """Runtime predictor backed by persisted prototype model artifacts."""

    def __init__(
        self,
        artifact_storage: ArtifactStorage | None = None,
    ) -> None:
        self._artifact_storage = artifact_storage
        self._model_payload: dict[str, Any] = {}

    async def load_model(self, model_ref: Any) -> None:
        if self._artifact_storage is None:
            raise ValueError("artifact_storage is required for TorchPredictor")
        if not model_ref.uri:
            raise ValueError("model_ref.uri is required")
        raw = await self._artifact_storage.get_bytes(model_ref.uri)
        try:
            self._model_payload = json.loads(raw.decode("utf-8"))
            return
        except Exception:
            pass

        metadata = model_ref.metadata if isinstance(model_ref.metadata, dict) else {}
        label_space = (
            metadata.get("label_space")
            if isinstance(metadata.get("label_space"), list)
            else []
        )
        if not label_space:
            raise ValueError(
                "model artifact is not a supported torch prototype payload"
            )

        dim = 64
        prototypes: dict[str, list[float]] = {}
        for idx, label in enumerate(str(item) for item in label_space if str(item)):
            vec = [0.0] * dim
            vec[idx % dim] = 1.0
            prototypes[label] = vec
        self._model_payload = {
            "framework": str(metadata.get("framework", "pytorch")),
            "architecture": str(metadata.get("architecture", "resnet50")),
            "label_space": list(prototypes.keys()),
            "label_prototypes": prototypes,
            "source": "metadata-fallback",
        }

    async def predict_batch(
        self, ctx: PredictContext, samples: list[Any]
    ) -> BatchPredictResult:
        predictions: list[PredictResult] = []
        failed = 0
        for sample in samples:
            pred = await self.predict_single(ctx, sample)
            predictions.append(pred)
            if pred.metadata.get("error"):
                failed += 1
        return BatchPredictResult(
            predictions=predictions,
            total=len(samples),
            successful=len(samples) - failed,
            failed=failed,
        )

    async def predict_single(self, ctx: PredictContext, sample: Any) -> PredictResult:
        sample_id = str(sample.get("sample_id", ""))
        image_bytes = sample.get("image_bytes")
        label_space = list(ctx.dataset_ref.label_space)
        if image_bytes is None:
            return PredictResult(
                sample_id=sample_id,
                label="",
                confidence=None,
                metadata={"error": "missing image bytes"},
            )
        embedding = _image_embedding_from_bytes(image_bytes)
        if ctx.target == "embedding":
            return PredictResult(
                sample_id=sample_id,
                label="embedding",
                confidence=1.0,
                raw_output=embedding,
                metadata={"embedding_dim": len(embedding)},
            )

        prototypes = self._model_payload.get("label_prototypes", {})
        if not isinstance(prototypes, dict):
            prototypes = {}
        if not prototypes and label_space:
            prototypes = {label: [0.0] * len(embedding) for label in label_space}

        scores: dict[str, float] = {}
        for label, proto in prototypes.items():
            if isinstance(proto, list) and proto:
                scores[str(label)] = _cosine(embedding, [float(x) for x in proto])
        if not scores:
            return PredictResult(
                sample_id=sample_id,
                label="",
                confidence=None,
                metadata={"error": "model has no label prototypes"},
            )
        best_label = max(scores.items(), key=lambda x: x[1])[0]
        total = sum(max(v, 0.0) for v in scores.values())
        confidence = max(scores[best_label], 0.0) / total if total > 0 else 0.0
        return PredictResult(
            sample_id=sample_id,
            label=best_label,
            confidence=confidence,
            scores=scores,
            metadata={"runtime": "torch-prototype"},
        )

    async def unload_model(self) -> None:
        self._model_payload = {}


# TorchTrainer removed — the legacy metadata["records"] pattern is always empty.
# Training now goes through flow-level @trainer decorators in flows/_trainers/.


async def predict_classification(
    ctx: PredictContext, sample: dict[str, Any], predictor: TorchPredictor
) -> dict[str, Any]:
    pred = await predictor.predict_single(ctx, sample)
    return {
        "label": pred.label,
        "confidence": pred.confidence,
        "scores": pred.scores,
        "metadata": pred.metadata,
    }


async def predict_embedding(
    ctx: PredictContext, sample: dict[str, Any], predictor: TorchPredictor
) -> dict[str, Any]:
    emb_ctx = PredictContext(
        job_id=ctx.job_id,
        trainer_id=ctx.trainer_id,
        model_ref=ctx.model_ref,
        dataset_ref=ctx.dataset_ref,
        target="embedding",
        config_overrides=ctx.config_overrides,
    )
    pred = await predictor.predict_single(emb_ctx, sample)
    return {
        "embedding": pred.raw_output,
        "metadata": pred.metadata,
    }
