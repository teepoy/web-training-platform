from __future__ import annotations

from typing import Any, TYPE_CHECKING

from app.runtime_compat.ml.demo.domain import (
    BatchPredictResult,
    ModelRef,
    PredictContext,
    PredictResult,
)

if TYPE_CHECKING:
    from app.runtime_compat.ml.demo.protocols import EmbeddingClient


class ClipPredictor:
    """Zero-shot image classifier via CLIP embedding service (classify_image / classify_batch)."""

    def __init__(self, embedding_client: EmbeddingClient) -> None:
        self._embedding_client: EmbeddingClient = embedding_client
        self._label_space: list[str] = []
        self._model_name: str = "openai/clip-vit-base-patch32"

    def load_model(self, model_ref: ModelRef) -> None:
        self._label_space = model_ref.metadata.get("label_space", [])
        if isinstance(self._label_space, str):
            self._label_space = [
                lbl.strip() for lbl in self._label_space.split(",") if lbl.strip()
            ]
        model_name = model_ref.metadata.get("model_name")
        if model_name:
            self._model_name = model_name

    def unload_model(self) -> None:
        self._label_space = []
        self._model_name = "openai/clip-vit-base-patch32"

    async def predict_single(
        self, ctx: PredictContext, sample: dict[str, Any]
    ) -> PredictResult:
        image_bytes = _extract_image_bytes(sample)
        if image_bytes is None:
            return PredictResult(
                sample_id=str(sample.get("id", "")),
                label="",
                confidence=0.0,
                metadata={"error": "no image_bytes in sample"},
            )

        labels = self._resolve_labels(ctx)
        if not labels:
            return PredictResult(
                sample_id=str(sample.get("id", "")),
                label="",
                confidence=0.0,
                metadata={"error": "no label space available"},
            )

        (
            predicted_label,
            confidence,
            scores,
        ) = await self._embedding_client.classify_image(
            image_bytes, labels, self._model_name
        )
        return PredictResult(
            sample_id=str(sample.get("id", "")),
            label=predicted_label,
            confidence=confidence,
            scores=scores,
        )

    async def predict_batch(
        self, ctx: PredictContext, samples: list[dict[str, Any]]
    ) -> BatchPredictResult:
        labels = self._resolve_labels(ctx)
        if not labels:
            failed_results = [
                PredictResult(
                    sample_id=str(s.get("id", "")),
                    label="",
                    confidence=0.0,
                    metadata={"error": "no label space available"},
                )
                for s in samples
            ]
            return BatchPredictResult(
                predictions=failed_results,
                total=len(samples),
                successful=0,
                failed=len(samples),
            )

        image_bytes_list: list[bytes] = []
        valid_indices: list[int] = []
        predictions: list[PredictResult] = []
        failed = 0

        for i, sample in enumerate(samples):
            img = _extract_image_bytes(sample)
            if img is None:
                predictions.append(
                    PredictResult(
                        sample_id=str(sample.get("id", "")),
                        label="",
                        confidence=0.0,
                        metadata={"error": "no image_bytes in sample"},
                    )
                )
                failed += 1
            else:
                image_bytes_list.append(img)
                valid_indices.append(i)

        if image_bytes_list:
            batch_results = await self._embedding_client.classify_batch(
                image_bytes_list, labels, self._model_name
            )
            batch_idx = 0
            for i in range(len(samples)):
                if i in valid_indices:
                    predicted_label, confidence, scores = batch_results[batch_idx]
                    predictions.insert(
                        i,
                        PredictResult(
                            sample_id=str(samples[i].get("id", "")),
                            label=predicted_label,
                            confidence=confidence,
                            scores=scores,
                        ),
                    )
                    batch_idx += 1

        return BatchPredictResult(
            predictions=predictions,
            total=len(samples),
            successful=len(samples) - failed,
            failed=failed,
        )

    def _resolve_labels(self, ctx: PredictContext) -> list[str]:
        return self._label_space or ctx.dataset_ref.label_space


def _make_clip_predictor(**kwargs: Any) -> ClipPredictor:
    embedding_client = kwargs.get("embedding_client")
    if embedding_client is None:
        raise ValueError("embedding_client is required for ClipPredictor")
    return ClipPredictor(embedding_client=embedding_client)


ClipPredictorFactory = _make_clip_predictor


def _extract_image_bytes(sample: dict[str, Any]) -> bytes | None:
    for key in ("image_bytes", "image", "data"):
        val = sample.get(key)
        if isinstance(val, bytes):
            return val
    return None
