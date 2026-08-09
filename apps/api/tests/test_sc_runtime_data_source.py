from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import polars as pl
import pytest

from app.modules.runtime.domain.context import TrainingRuntimeContext
from app.modules.sc.runtime.data_source import open_sc_runtime_source
from app.shared.api.schemas import Dataset, TaskSpec


@pytest.mark.asyncio
async def test_dataset_runtime_source_reuses_storage_metadata_without_direct_session() -> None:
    dataset = Dataset(
        id="dataset-1",
        org_id="org-1",
        name="SC dataset",
        dataset_type="image_sc",
        task_spec=TaskSpec(label_space=["scratch", "particle"]),
        view_types=["sc.patch_image.v1"],
    )
    calls: list[tuple[str, object]] = []

    class Storage:
        async def get_dataset_metadata(self) -> Dataset:
            calls.append(("metadata", None))
            return dataset

        async def list_samples(self, **kwargs: object) -> pl.LazyFrame:
            calls.append(("samples", kwargs))
            return pl.LazyFrame(
                {
                    "id": ["sample-1"],
                    "dataset_id": ["dataset-1"],
                    "metadata_json": [
                        {
                            "sample_id": "upstream-sample-1",
                            "defect_id": "defect-1",
                            "inspection_time": "2026-08-07",
                        }
                    ],
                }
            )

    storage = Storage()

    class StorageFactory:
        async def open(self, dataset_id: str, org_id: str) -> Storage:
            calls.append(("open", (dataset_id, org_id)))
            return storage

    class Injector:
        def get(self, _interface: object) -> StorageFactory:
            return StorageFactory()

    class ForbiddenSessionFactory:
        def __call__(self) -> None:
            raise AssertionError("runtime source must not read DatasetORM directly")

    app_context = cast(
        Any,
        SimpleNamespace(
            injector=Injector(),
            shared=SimpleNamespace(session_factory=ForbiddenSessionFactory()),
        ),
    )
    runtime_ctx = TrainingRuntimeContext(
        app_context=app_context,
        job_id="job-1",
        dataset_id="dataset-1",
        trainer_id="resnet50-sc-v1",
        created_by="user-1",
        org_id="org-1",
        sample_ids=["sample-1"],
    )

    async with open_sc_runtime_source(
        runtime_ctx,
        with_labels=True,
        with_predictions=False,
    ) as source:
        assert source.dataset_type == "image_sc"
        assert source.view_types == ("sc.patch_image.v1",)
        assert source.label_space == ("scratch", "particle")
        assert source.rows.collect().to_dicts() == [
            {
                "sample_id": "sample-1",
                "defect_id": "defect-1",
                "inspection_time": "2026-08-07",
            }
        ]

    assert calls == [
        ("open", ("dataset-1", "org-1")),
        ("metadata", None),
        (
            "samples",
            {
                "return_lazyframe": True,
                "with_labels": True,
                "with_predictions": False,
                "sample_ids": ["sample-1"],
            },
        ),
    ]
