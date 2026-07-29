from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.modules.storage.domain.sparse.models import DatasetManifest

from app.modules.datasets.app.services.dataset_service import DatasetService
from app.modules.datasets.domain.status import DatasetTrainDisabledReason
from app.shared.api.schemas import Dataset, DatasetStorageMode


class _PayloadStore:
    async def get_manifest(self, dataset_id: str, org_id: str) -> DatasetManifest:
        return DatasetManifest(
            dataset_id=dataset_id,
            storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE.value,
            shard_count=1,
            total_rows=37,
        )


class _Storage:
    def __init__(self, label_counts: dict[str, int]) -> None:
        self._label_counts = label_counts

    async def get_annotation_stats(self) -> dict[str, object]:
        return {
            "total_samples": 10,
            "annotated_samples": sum(self._label_counts.values()),
            "label_counts": self._label_counts,
        }


class _StorageFactory:
    def __init__(self, label_counts: dict[str, int]) -> None:
        self._storage = _Storage(label_counts)

    async def open(self, dataset_id: str, org_id: str) -> _Storage:
        return self._storage


def _service(label_counts: dict[str, int] | None = None) -> DatasetService:
    return DatasetService(
        repository=cast(Any, SimpleNamespace()),
        storage_factory=cast(Any, _StorageFactory(label_counts or {})),
        payload_store=cast(Any, _PayloadStore()),
        config=cast(
            Any,
            SimpleNamespace(
                label_studio=SimpleNamespace(
                    external_url="", url="http://label-studio"
                )
            ),
        ),
    )


@pytest.mark.asyncio
async def test_dataset_list_response_includes_sparse_sample_count() -> None:
    dataset = Dataset(
        id="dataset-1",
        name="patch dataset",
        dataset_type="image_sc",
        org_id="org-1",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={"task_type": "classification"},
    )

    response = await _service().to_list_response(dataset)

    assert response.dataset_meta["sample_count"] == 37
    assert response.dataset_meta["total_samples"] == 37


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label_counts", "expected_active_class_count", "expected_allow_train"),
    [
        ({}, 0, False),
        ({"cat": 3, "dog": 0}, 1, False),
        ({"cat": 3, "dog": 1}, 2, True),
    ],
)
async def test_dataset_status_requires_two_active_classes(
    label_counts: dict[str, int],
    expected_active_class_count: int,
    expected_allow_train: bool,
) -> None:
    status = await _service(label_counts).get_status("dataset-1", "org-1")

    assert status.minimum_active_class_count == 2
    assert status.active_class_count == expected_active_class_count
    assert status.allow_train is expected_allow_train
    assert status.train_disabled_reason is (
        None
        if expected_allow_train
        else DatasetTrainDisabledReason.INSUFFICIENT_ACTIVE_CLASSES
    )
