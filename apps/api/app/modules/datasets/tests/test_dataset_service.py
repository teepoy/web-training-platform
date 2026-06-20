from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from platform_runtime.sparse.models import DatasetManifest

from app.modules.datasets.app.services.dataset_service import DatasetService
from app.shared.api.schemas import Dataset, DatasetStorageMode


class _PayloadStore:
    async def get_manifest(self, dataset_id: str, org_id: str) -> DatasetManifest:
        return DatasetManifest(
            dataset_id=dataset_id,
            storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE.value,
            shard_count=1,
            total_rows=37,
        )


def _service() -> DatasetService:
    return DatasetService(
        repository=cast(Any, SimpleNamespace()),
        storage_factory=cast(Any, SimpleNamespace()),
        ls_client=cast(Any, SimpleNamespace()),
        storage=cast(Any, SimpleNamespace()),
        payload_store=cast(Any, _PayloadStore()),
        capability_guard=lambda dataset: None,
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
