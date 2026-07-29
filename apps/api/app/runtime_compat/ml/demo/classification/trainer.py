from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Callable

from app.runtime_compat.ml.demo.domain import TrainContext, TrainResult

from ._utils import _decode_data_uri, _image_embedding_from_bytes, _logger

if TYPE_CHECKING:
    from app.runtime_compat.ml.demo.protocols import ArtifactStorage


class ClassificationTrainer:
    """Concrete trainer that persists a prototype classifier model artifact."""

    def __init__(
        self,
        artifact_storage: ArtifactStorage | None = None,
        embed_fn: Callable[[bytes], list[float]] | None = None,
    ) -> None:
        self._artifact_storage = artifact_storage
        self._embed_fn = embed_fn

    async def train(self, ctx: TrainContext) -> TrainResult:
        if self._artifact_storage is None:
            raise ValueError("artifact_storage is required for ClassificationTrainer")
        logger = _logger()
        records = ctx.dataset_ref.metadata.get("records", [])
        if not isinstance(records, list):
            records = []

        grouped: dict[str, list[list[float]]] = defaultdict(list)
        label_space = list(ctx.dataset_ref.label_space)
        processed = 0
        skipped = 0
        for row in records:
            if not isinstance(row, dict):
                skipped += 1
                continue
            label = str(row.get("label", ""))
            if not label:
                skipped += 1
                continue
            if label_space and label not in label_space:
                skipped += 1
                continue

            embedded_bytes = row.get("image_bytes")
            if isinstance(embedded_bytes, bytes) and embedded_bytes:
                image_bytes: bytes = embedded_bytes
            else:
                image_uri = str(row.get("image_uri", ""))
                if not image_uri:
                    skipped += 1
                    continue
                try:
                    if image_uri.startswith("data:"):
                        image_bytes = _decode_data_uri(image_uri)
                    else:
                        image_bytes = await self._artifact_storage.get_bytes(image_uri)
                except (FileNotFoundError, OSError, ValueError):
                    skipped += 1
                    continue
            grouped[label].append(
                _image_embedding_from_bytes(image_bytes, embed_fn=self._embed_fn)
            )
            processed += 1

        if not grouped:
            raise ValueError(
                "no labeled samples with readable images found for training"
            )

        prototypes: dict[str, list[float]] = {}
        for label, vectors in grouped.items():
            dim = len(vectors[0])
            acc = [0.0] * dim
            for vec in vectors:
                for idx, val in enumerate(vec):
                    acc[idx] += val
            mean_vec = [v / len(vectors) for v in acc]
            norm = math.sqrt(sum(x * x for x in mean_vec))
            if norm > 0:
                mean_vec = [x / norm for x in mean_vec]
            prototypes[label] = mean_vec

        model_object = f"models/{ctx.job_id}/model.json"
        metrics_object = f"models/{ctx.job_id}/metrics.json"
        model_payload = {
            "framework": "pytorch",
            "architecture": ctx.model_ref.architecture or "resnet50",
            "created_at": datetime.now(UTC).isoformat(),
            "label_space": sorted(list(prototypes.keys())),
            "label_prototypes": prototypes,
        }
        metrics_payload = {
            "trained_samples": processed,
            "skipped_samples": skipped,
            "labels": {k: len(v) for k, v in grouped.items()},
        }
        model_uri = await self._artifact_storage.put_bytes(
            object_name=model_object,
            data=json.dumps(model_payload, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )
        metrics_uri = await self._artifact_storage.put_bytes(
            object_name=metrics_object,
            data=json.dumps(metrics_payload, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )
        logger.info(
            "Classification training finished job_id=%s processed=%s",
            ctx.job_id,
            processed,
        )
        return TrainResult(
            model_uri=model_uri,
            metrics=metrics_payload,
            artifact_uris=[model_uri, metrics_uri],
            metadata={
                "runtime": "classification-prototype",
                "framework": ctx.model_ref.framework,
                "architecture": ctx.model_ref.architecture,
                "trained_samples": processed,
            },
        )
