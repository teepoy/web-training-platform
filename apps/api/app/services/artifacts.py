from __future__ import annotations

import hashlib
import json
from typing import Any, Callable
from urllib.parse import urlparse

from app.domain.models import (
    Annotation,
    AnnotationVersion,
    ArtifactRef,
    Dataset,
    PredictionReviewAction,
    Sample,
)


# ---------------------------------------------------------------------------
# Export format registry (strategy pattern)
# ---------------------------------------------------------------------------

ExportBuilder = Callable[..., dict[str, Any]]

_FORMAT_REGISTRY: dict[str, ExportBuilder] = {}


def register_format(format_id: str) -> Callable[[ExportBuilder], ExportBuilder]:
    """Decorator to register an export format builder."""
    def decorator(fn: ExportBuilder) -> ExportBuilder:
        _FORMAT_REGISTRY[format_id] = fn
        return fn
    return decorator


def list_export_formats() -> list[dict[str, str]]:
    """Return metadata for all registered export formats."""
    return [{"format_id": fid} for fid in sorted(_FORMAT_REGISTRY)]


def get_export_builder(format_id: str) -> ExportBuilder:
    """Look up an export builder by format_id. Raises KeyError if unknown."""
    return _FORMAT_REGISTRY[format_id]


# ---------------------------------------------------------------------------
# Built-in export formats
# ---------------------------------------------------------------------------


@register_format("annotation-version-full-context-v1")
def build_full_context_export(
    *,
    review_action: PredictionReviewAction,
    dataset: Dataset,
    samples: list[Sample],
    annotations: list[Annotation],
    versions: list[AnnotationVersion],
) -> dict[str, Any]:
    """Full-context JSON export: review action, dataset, touched samples, annotations+versions."""
    # Build annotation lookup: annotation_id -> (Annotation, AnnotationVersion)
    ann_map: dict[str, Annotation] = {a.id: a for a in annotations}
    entries: list[dict[str, Any]] = []
    for v in versions:
        ann = ann_map.get(v.annotation_id)
        if ann is None:
            continue
        entries.append({
            "annotation": ann.model_dump(mode="json"),
            "version": v.model_dump(mode="json"),
            "prediction_context": {
                "prediction_id": v.prediction_id,
                "predicted_label": v.predicted_label,
            },
        })
    return {
        "format": "annotation-version-full-context-v1",
        "review_action": review_action.model_dump(mode="json"),
        "dataset": dataset.model_dump(mode="json"),
        "samples": [s.model_dump(mode="json") for s in samples],
        "annotations": entries,
    }


@register_format("annotation-version-compact-v1")
def build_compact_export(
    *,
    review_action: PredictionReviewAction,
    dataset: Dataset,
    samples: list[Sample],
    annotations: list[Annotation],
    versions: list[AnnotationVersion],
) -> dict[str, Any]:
    """Compact export: flat rows of (sample_id, predicted_label, final_label, confidence)."""
    ann_map: dict[str, Annotation] = {a.id: a for a in annotations}
    rows: list[dict[str, Any]] = []
    for v in versions:
        ann = ann_map.get(v.annotation_id)
        if ann is None:
            continue
        rows.append({
            "sample_id": ann.sample_id,
            "predicted_label": v.predicted_label,
            "final_label": v.final_label,
            "confidence": v.confidence,
        })
    return {
        "format": "annotation-version-compact-v1",
        "review_action_id": review_action.id,
        "dataset_id": dataset.id,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Artifact service
# ---------------------------------------------------------------------------


class ArtifactService:
    def __init__(self, storage, repository) -> None:
        self.storage = storage
        self.repository = repository

    async def persist_dataset_export(self, dataset: Dataset, samples: list[Sample], annotations: list[Annotation]) -> str:
        payload = self.build_dataset_export(dataset, samples, annotations)
        object_name = f"exports/{dataset.id}/dataset-export.json"
        return await self.storage.put_bytes(object_name=object_name, data=json.dumps(payload).encode("utf-8"), content_type="application/json")

    async def persist_version_export(
        self,
        review_action: PredictionReviewAction,
        dataset: Dataset,
        samples: list[Sample],
        annotations: list[Annotation],
        versions: list[AnnotationVersion],
        format_id: str = "annotation-version-full-context-v1",
    ) -> str:
        """Build and persist an annotation-version export."""
        builder = get_export_builder(format_id)
        payload = builder(
            review_action=review_action,
            dataset=dataset,
            samples=samples,
            annotations=annotations,
            versions=versions,
        )
        object_name = f"exports/{dataset.id}/review-{review_action.id}/{format_id}.json"
        return await self.storage.put_bytes(
            object_name=object_name,
            data=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )

    async def persist_job_artifacts(self, job_id: str, artifacts: list[ArtifactRef]) -> list[ArtifactRef]:
        """Persist artifacts to repository.
        
        If artifacts already have real storage URIs (s3://, memory://), they are 
        stored directly. Legacy artifacts with placeholder URIs get re-wrapped.
        """
        persisted: list[ArtifactRef] = []
        for artifact in artifacts:
            if self._looks_like_real_storage_uri(artifact.uri):
                persisted.append(artifact)
            else:
                # Legacy path: wrap metadata as JSON and store
                content = json.dumps(
                    {
                        "source_uri": artifact.uri,
                        "kind": artifact.kind,
                        "metadata": artifact.metadata,
                    },
                    sort_keys=True,
                ).encode("utf-8")
                checksum = hashlib.sha256(content).hexdigest()
                object_name = f"artifacts/{job_id}/{artifact.id}.json"
                stored_uri = await self.storage.put_bytes(
                    object_name=object_name,
                    data=content,
                    content_type="application/json",
                )
                persisted.append(
                    ArtifactRef(
                        id=artifact.id,
                        uri=stored_uri,
                        kind=artifact.kind,
                        metadata={
                            **artifact.metadata,
                            "source_uri": artifact.uri,
                            "checksum_sha256": checksum,
                        },
                    )
                )
        await self.repository.add_artifacts(job_id, persisted)
        return persisted

    @staticmethod
    def _looks_like_real_storage_uri(uri: str) -> bool:
        parsed = urlparse(uri)
        if parsed.scheme == "memory":
            return bool(parsed.path)
        if parsed.scheme == "s3":
            return bool(parsed.netloc and parsed.path and parsed.path != "/")
        return False

    def build_dataset_export(self, dataset: Dataset, samples: list[Sample], annotations: list[Annotation]) -> dict:
        return {
            "format": "hf-datasets-friendly-json",
            "dataset": dataset.model_dump(mode="json"),
            "samples": [s.model_dump(mode="json") for s in samples],
            "annotations": [a.model_dump(mode="json") for a in annotations],
            "artifact_layout": {
                "dataset_snapshot": "s3://artifacts/{tenant}/{project}/{task}/{job}/dataset_snapshot/",
                "model": "s3://artifacts/{tenant}/{project}/{task}/{job}/model/",
            },
        }
