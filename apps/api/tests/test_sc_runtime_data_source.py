from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import polars as pl
import pytest

from app.modules.runtime.domain.context import TrainingRuntimeContext
from app.modules.dataset_collections.domain.models import DatasetCollectionRevision
from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.datasets.domain.entities import (
    DatasetRevision,
    DatasetRevisionOperation,
)
from app.modules.datasets.port.local import DatasetRevisionReaderPort
from app.modules.sc.runtime.data_source import open_sc_runtime_source
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.api.schemas import Dataset, ImageSourceBinding, TaskSpec


@pytest.mark.asyncio
async def test_dataset_runtime_source_reuses_storage_metadata_without_direct_session() -> (
    None
):
    dataset = Dataset(
        id="dataset-1",
        org_id="org-1",
        name="SC dataset",
        dataset_type="image_sc",
        task_spec=TaskSpec(label_space=["scratch", "particle"]),
        view_types=["sc.patch_image.v1"],
        image_source=ImageSourceBinding(
            contract="sc.patch_archive.v1",
            profile="sc_upstream",
        ),
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
        trainer_id="yolo-sc-v1",
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
        assert source.image_source_profiles == {"dataset-1": "sc_upstream"}
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


@pytest.mark.asyncio
async def test_observed_collection_runtime_resolves_current_member_data() -> None:
    now = datetime.now(timezone.utc)
    collection_revision = DatasetCollectionRevision(
        id="collection-revision-1",
        collection_id="collection-1",
        revision_number=1,
        definition_version=1,
        definition_hash="definition-hash",
        target_view_id="sc.patch_image.v1",
        target_view_contract="sc.patch-image",
        target_schema_version="1",
        status="ready",
        source_snapshot=(
            {
                "member_id": "member-1",
                "source_dataset_id": "dataset-1",
                "label_space": ["scratch", "particle"],
            },
        ),
        row_count=None,
        label_counts={},
        manifest_uri="memory://collection-manifest.json",
        provenance_uri=None,
        trigger_kind="manual",
        trigger_ref=None,
        created_by="user-1",
        created_at=now,
        error_code=None,
        error_detail=None,
        manifest_format="collection-composite-observed.v1",
        source_resolution="observed",
        reproducibility_capability=False,
    )

    class Storage:
        async def get_dataset_metadata(self) -> Dataset:
            return Dataset(
                id="dataset-1",
                org_id="org-1",
                name="SC dataset",
                dataset_type="image_sc",
                task_spec=TaskSpec(label_space=["scratch", "particle"]),
                view_types=["sc.patch_image.v1"],
                image_source=ImageSourceBinding(
                    contract="sc.patch_archive.v1",
                    profile="member-folder",
                ),
            )

        async def list_samples(self, **_kwargs: object) -> pl.LazyFrame:
            return pl.LazyFrame(
                {
                    "sample_id": ["sample-1"],
                    "defect_id": [42],
                    "label": ["scratch"],
                }
            )

    class StorageFactory:
        async def open(self, dataset_id: str, org_id: str) -> Storage:
            assert (dataset_id, org_id) == ("dataset-1", "org-1")
            return Storage()

    class CollectionReader:
        async def get_revision(
            self, collection_id: str, revision_id: str, org_id: str
        ) -> DatasetCollectionRevision:
            assert (collection_id, revision_id, org_id) == (
                "collection-1",
                "collection-revision-1",
                "org-1",
            )
            return collection_revision

    class DatasetRevisionReader:
        async def resolve_or_create_baseline(
            self, *, dataset_id: str, org_id: str, created_by: str
        ) -> DatasetRevision:
            assert (dataset_id, org_id, created_by) == (
                "dataset-1",
                "org-1",
                "user-1",
            )
            return DatasetRevision(
                id="dataset-revision-at-launch",
                dataset_id=dataset_id,
                revision_number=2,
                manifest_uri="memory://dataset-audit-manifest.json",
                operation=DatasetRevisionOperation.BATCH_EDIT,
                created_by=created_by,
                created_at=now,
            )

    class Injector:
        def get(self, interface: object) -> object:
            if interface is DatasetCollectionRevisionReaderPort:
                return CollectionReader()
            if interface is DatasetStorageFactoryPort:
                return StorageFactory()
            if interface is DatasetRevisionReaderPort:
                return DatasetRevisionReader()
            raise AssertionError(f"Unexpected dependency: {interface}")

    class ForbiddenArtifactStorage:
        async def get_file(self, _uri: str, _destination: str) -> None:
            raise AssertionError("observed Collection must not read legacy artifact")

    app_context = cast(
        Any,
        SimpleNamespace(
            injector=Injector(),
            shared=SimpleNamespace(artifact_storage=ForbiddenArtifactStorage()),
        ),
    )
    runtime_ctx = TrainingRuntimeContext(
        app_context=app_context,
        job_id="job-1",
        dataset_id=None,
        trainer_id="yolo-sc-v1",
        created_by="user-1",
        org_id="org-1",
        collection_id="collection-1",
        collection_revision_id="collection-revision-1",
    )

    async with open_sc_runtime_source(
        runtime_ctx,
        with_labels=True,
        with_predictions=False,
    ) as source:
        assert source.rows.collect().to_dicts() == [
            {
                "sample_id": "dataset-1::sample-1",
                "defect_id": 42,
                "label": "scratch",
                "source_sample_id": "sample-1",
                "source_dataset_id": "dataset-1",
                "collection_member_id": "member-1",
                "row_key": "dataset-1::sample-1",
            }
        ]
        assert source.resolved_dataset_revision_ids == ("dataset-revision-at-launch",)
        assert source.image_source_profiles == {"dataset-1": "member-folder"}
