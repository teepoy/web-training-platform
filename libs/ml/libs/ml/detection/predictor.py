"""Detection predictor using prototype-based cosine similarity on 8×8 gray embeddings.

Backed by persisted prototype model artifacts (JSON).  For each sample,
computes a 64-dim image embedding, compares against label prototypes via
cosine similarity, and returns the predicted label with a default full-image
bounding box.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from libs.ml.domain import (
    BatchPredictResult,
    PredictContext,
    PredictResult,
)

from ..classification._utils import _cosine, _image_embedding_from_bytes

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from libs.ml.protocols import ArtifactStorage


class DetectionPredictor:
    """Runtime detection predictor backed by persisted prototype model artifacts.

    Uses 8×8 grayscale embeddings and cosine similarity for prototype
    matching.  Returns a default full-image bounding box alongside the
    predicted label and confidence.
    """

    def __init__(
        self,
        artifact_storage: ArtifactStorage | None = None,
    ) -> None:
        self._artifact_storage = artifact_storage
        self._model_payload: dict[str, Any] = {}

    async def load_model(self, model_ref: Any) -> None:
        """Load prototype JSON from artifact storage.

        Falls back to generating one-hot prototypes from label_space in
        *model_ref.metadata* when the artifact is not valid JSON.
        """
        if self._artifact_storage is None:
            raise ValueError("artifact_storage is required for DetectionPredictor")
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
                "model artifact is not a supported detection prototype payload"
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
        _logger.info("Detection predict_batch started — %d samples", len(samples))
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
            "Detection predict_batch finished — %d/%d successful (%.1f samples/s)",
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
        """Predict single sample via cosine similarity to stored prototypes.

        Returns a default full-image bounding box in ``raw_output`` alongside
        the best label and its confidence.
        """
        sample_id = str(sample.get("sample_id", ""))
        image_bytes = sample.get("image_bytes")
        if image_bytes is None:
            return PredictResult(
                sample_id=sample_id,
                label="",
                confidence=None,
                metadata={"error": "missing image bytes"},
            )
        embedding = _image_embedding_from_bytes(image_bytes)

        prototypes = self._model_payload.get("label_prototypes", {})
        if not isinstance(prototypes, dict):
            prototypes = {}

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

        # Detection-specific default full-image bounding box
        default_bbox = {"x": 0.0, "y": 0.0, "width": 224.0, "height": 224.0}

        return PredictResult(
            sample_id=sample_id,
            label=best_label,
            confidence=confidence,
            scores=scores,
            raw_output={"boxes": [default_bbox], "label": best_label},
            metadata={"runtime": "detection-prototype"},
        )

    async def unload_model(self) -> None:
        """Clear the in-memory model payload."""
        self._model_payload = {}
