from __future__ import annotations

from typing import Any, cast

import pytest
import polars as pl

from app.modules.sc.wafer_data_gen import build_patch_sample
from app.modules.sc.app.services.training_images import normalize_sc_training_row
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.training.app.services.readiness import TrainingReadinessService
from app.shared.api.schemas import Dataset, TaskSpec
from app.shared.infrastructure.storage import InMemoryArtifactStorage


class _Storage:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def list_samples(self, **_kwargs: Any) -> Any:
        return pl.DataFrame(self._rows, infer_schema_length=None).lazy()


class _StorageFactory:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._storage = _Storage(rows)

    async def open(self, _dataset_id: str, org_id: str | None = None) -> _Storage:
        _ = org_id
        return self._storage


def _factory(rows: list[dict[str, Any]]) -> DatasetStorageFactoryPort:
    return cast(DatasetStorageFactoryPort, _StorageFactory(rows))


def _dataset() -> Dataset:
    return Dataset(
        id="dataset-1",
        org_id="org-1",
        name="readiness-test",
        dataset_type="image_sc",
        task_spec=TaskSpec(task_type="sc", label_space=["Scratch", "Particle"]),
    )


def _classification_dataset() -> Dataset:
    return Dataset(
        id="dataset-2",
        org_id="org-1",
        name="classification-readiness-test",
        dataset_type="classification",
        task_spec=TaskSpec(task_type="classification", label_space=["Cat", "Dog"]),
    )


def _row(index: int, label: str, *, with_images: bool = True) -> dict[str, Any]:
    sample = build_patch_sample(index)
    shard_images = [
        image.model_dump(mode="json")
        for image in sample.shard_images
    ]
    return {
        "id": f"sample-{index}",
        "image_uris": (
            [image.image_id for image in sample.shard_images] if with_images else []
        ),
        "metadata_json": {
            "sample_id": f"sample-{index}",
            "inspection_time": sample.inspection_time.isoformat()
            if sample.inspection_time
            else "",
            "wafer_key": sample.wafer_key,
            "defect_id": sample.defect_id,
            "shard_images": shard_images if with_images else [],
        },
        "label": label,
    }


@pytest.mark.asyncio
async def test_readiness_accepts_two_labels_with_real_inline_images() -> None:
    rows = [_row(0, "Scratch"), _row(1, "Particle")]
    service = TrainingReadinessService(
        storage_factory=_factory(rows),
        artifact_storage=InMemoryArtifactStorage(),
    )

    report = await service.assess(
        dataset=_dataset(),
        sample_ids=None,
        sample_filter=None,
        missing_image_policy="skip",
    )

    assert report.ready
    assert report.readable_samples == 2
    assert report.runtime_resolvable_samples == 0
    assert report.active_labels == ["Particle", "Scratch"]


@pytest.mark.asyncio
async def test_class_readiness_accepts_two_active_labels() -> None:
    service = TrainingReadinessService(
        storage_factory=_factory(
            [
                {"id": "sample-1", "label": "Cat"},
                {"id": "sample-2", "label": "Dog"},
            ]
        ),
        artifact_storage=InMemoryArtifactStorage(),
    )

    report = await service.assess_classes(dataset=_classification_dataset())

    assert report.ready
    assert report.annotated_samples == 2
    assert report.active_labels == ["Cat", "Dog"]


@pytest.mark.asyncio
async def test_class_readiness_rejects_one_active_label() -> None:
    service = TrainingReadinessService(
        storage_factory=_factory(
            [
                {"id": "sample-1", "label": "Cat"},
                {"id": "sample-2", "label": "Cat"},
            ]
        ),
        artifact_storage=InMemoryArtifactStorage(),
    )

    report = await service.assess_classes(dataset=_classification_dataset())

    assert not report.ready
    assert report.active_labels == ["Cat"]
    assert "at least 2 active labels" in report.failure_reasons[-1]


@pytest.mark.asyncio
async def test_readiness_scans_multiple_bounded_batches() -> None:
    rows = [
        _row(index, "Scratch" if index % 2 == 0 else "Particle")
        for index in range(65)
    ]
    service = TrainingReadinessService(
        storage_factory=_factory(rows),
        artifact_storage=InMemoryArtifactStorage(),
    )

    report = await service.assess(
        dataset=_dataset(),
        sample_ids=None,
        sample_filter=None,
        missing_image_policy="skip",
    )

    assert report.ready
    assert report.annotated_samples == 65
    assert report.readable_samples == 65


@pytest.mark.asyncio
async def test_readiness_applies_skip_before_active_label_validation() -> None:
    unusable = _row(2, "Ignored", with_images=False)
    unusable["metadata_json"]["inspection_time"] = ""
    rows = [
        _row(0, "Scratch"),
        _row(1, "Particle"),
        unusable,
    ]
    service = TrainingReadinessService(
        storage_factory=_factory(rows),
        artifact_storage=InMemoryArtifactStorage(),
    )

    report = await service.assess(
        dataset=_dataset(),
        sample_ids=None,
        sample_filter=None,
        missing_image_policy="skip",
    )

    assert report.ready
    assert report.skipped_samples == 1
    assert report.usable_samples == 2
    assert report.active_labels == ["Particle", "Scratch"]


@pytest.mark.asyncio
async def test_readiness_accepts_v3_scalar_rows_for_runtime_resolution() -> None:
    rows = [
        _row(0, "Scratch", with_images=False),
        _row(1, "Particle", with_images=False),
    ]
    service = TrainingReadinessService(
        storage_factory=_factory(rows),
        artifact_storage=InMemoryArtifactStorage(),
    )

    report = await service.assess(
        dataset=_dataset(),
        sample_ids=None,
        sample_filter=None,
        missing_image_policy="skip",
    )

    assert report.ready
    assert report.readable_samples == 0
    assert report.runtime_resolvable_samples == 2
    assert report.skipped_samples == 0
    assert report.active_labels == ["Particle", "Scratch"]


@pytest.mark.asyncio
async def test_readiness_rejects_scalar_row_without_upstream_identity() -> None:
    sample = build_patch_sample(0)
    row = _row(0, "Scratch", with_images=False)
    row["image_uris"] = [image.image_id for image in sample.shard_images]
    row["metadata_json"]["review_images"] = [
        image.model_dump(mode="json") for image in sample.review_images
    ]
    row["metadata_json"]["defect_id"] = ""
    service = TrainingReadinessService(
        storage_factory=_factory([row]),
        artifact_storage=InMemoryArtifactStorage(),
    )

    report = await service.assess(
        dataset=_dataset(),
        sample_ids=None,
        sample_filter=None,
        missing_image_policy="skip",
    )

    assert not report.ready
    assert report.readable_samples == 0
    assert report.unusable_samples == 1


def test_training_row_rejects_corrupt_metadata_json() -> None:
    with pytest.raises(ValueError, match="metadata must be valid JSON"):
        normalize_sc_training_row({"metadata_json": "{"})
