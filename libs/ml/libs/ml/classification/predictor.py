from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from libs.ml.domain import (
    BatchPredictResult,
    PredictContext,
    PredictResult,
)

from ._utils import _cosine, _image_embedding_from_bytes

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from libs.ml.protocols import ArtifactStorage, EmbeddingClient


class ClassificationPredictor:
    """Runtime predictor backed by persisted prototype model artifacts."""

    def __init__(
        self,
        embedding_client: EmbeddingClient | None = None,
        artifact_storage: ArtifactStorage | None = None,
        embed_fn: Callable[[bytes], list[float]] | None = None,
    ) -> None:
        self._embedding_client = embedding_client
        self._artifact_storage = artifact_storage
        self._embed_fn = embed_fn
        self._model_payload: dict[str, Any] = {}

    async def load_model(self, model_ref: Any) -> None:
        if self._artifact_storage is None:
            raise ValueError("artifact_storage is required for ClassificationPredictor")
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
                "model artifact is not a supported classification prototype payload"
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
        _logger.info("Classification predict_batch started — %d samples", len(samples))
        t_start = time.monotonic()
        predictions: list[PredictResult] = []
        failed = 0
        for sample in samples:
            pred = await self.predict_single(ctx, sample)
            predictions.append(pred)
            if pred.metadata.get("error"):
                failed += 1
        elapsed = time.monotonic() - t_start
        _logger.info(
            "Classification predict_batch finished — %d/%d successful (%.1f samples/s)",
            len(samples) - failed,
            len(samples),
            len(samples) / elapsed if elapsed > 0 else 0,
        )
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
        embedding = _image_embedding_from_bytes(image_bytes, embed_fn=self._embed_fn)
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
            metadata={"runtime": "classification-prototype"},
        )

    async def unload_model(self) -> None:
        self._model_payload = {}
