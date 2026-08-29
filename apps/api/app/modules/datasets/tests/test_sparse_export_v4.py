from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.modules.datasets.app.services.sparse_export import SparseExportAssembler
from app.modules.sc.schema import SC_SOURCE_SCHEMA_VERSION_V4
from app.modules.storage.domain.sparse import (
    ColumnSchema,
    DatasetManifest,
    ShardEntry,
    SparseIndexEntry,
)
from app.shared.api.schemas import Dataset, DatasetStorageMode
from app.shared.domain.protocols import ArtifactStorage


class _Store:
    def __init__(self, manifest: DatasetManifest) -> None:
        self.manifest = manifest

    async def get_manifest(self, dataset_id: str, org_id: str) -> DatasetManifest:
        del dataset_id, org_id
        return self.manifest


class _Reader:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.columns: list[list[str] | None] = []

    async def read_row_batch(
        self, *_args: object, columns: list[str] | None = None, **_kwargs: object
    ) -> list[dict[str, object]]:
        self.columns.append(columns)
        return self.rows


class _Storage:
    async def list_prefix(self, prefix: str) -> list[str]:
        del prefix
        return []


class _ScalarRows:
    def all(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(sample_id="sample-1", label="scratch")]


class _ExecuteResult:
    def scalars(self) -> _ScalarRows:
        return _ScalarRows()


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, _statement: object) -> _ExecuteResult:
        return _ExecuteResult()


def _session_factory() -> _Session:
    return _Session()


@pytest.mark.asyncio
async def test_v4_generic_export_reads_identity_shard_and_scalable_annotations() -> (
    None
):
    manifest = DatasetManifest(
        dataset_id="dataset-v4",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE.value,
        shard_count=1,
        total_rows=1,
        schema_columns=[
            ColumnSchema(name="sample_id", type="string"),
            ColumnSchema(name="defect_id", type="string"),
        ],
        shards=[
            ShardEntry(
                shard_index=0,
                uri="memory://identity.parquet",
                row_count=1,
                checksum_sha256="0" * 64,
                byte_size=1,
            )
        ],
        index=SparseIndexEntry(
            uri="memory://index.parquet",
            row_count=1,
            checksum_sha256="1" * 64,
            byte_size=1,
        ),
        manifest_version="v3",
        schema_version=SC_SOURCE_SCHEMA_VERSION_V4,
    )
    reader = _Reader(
        [{"sample_id": "sample-1", "defect_id": "defect-7", "ignored": "legacy"}]
    )
    assembler = SparseExportAssembler(
        store=cast(Any, _Store(manifest)),
        reader=cast(Any, reader),
        storage=cast(ArtifactStorage, _Storage()),
        session_factory=cast(Any, _session_factory),
    )
    dataset = Dataset(
        id="dataset-v4",
        name="Identity Dataset",
        dataset_type="image_sc",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={
            "source_inspection_time": "2026-08-29T08:00:00+08:00",
            "source_wafer_key": 17,
        },
    )

    export = await assembler.assemble(dataset, "org-1")

    assert export["format"] == "sparse-export-v4"
    assert reader.columns == [["sample_id", "defect_id"]]
    assert export["samples"] == [
        {
            "sample_id": "sample-1",
            "defect_id": "defect-7",
            "image_uri": None,
            "defective_uri": "/api/v1/sc/images/2026-08-29T08%3A00%3A00%2B08%3A00/17/defect-7/defective",
            "reference_uri": "/api/v1/sc/images/2026-08-29T08%3A00%3A00%2B08%3A00/17/defect-7/template",
            "metadata": {
                "defect_id": "defect-7",
                "inspection_time": "2026-08-29T08:00:00+08:00",
                "wafer_key": 17,
            },
            "images": [
                {
                    "image_id": "sample-1_template",
                    "image_type": "template",
                    "role": "patch_template",
                    "content_type": "image/png",
                    "filename": "template.png",
                    "access_url": "/api/v1/sc/images/2026-08-29T08%3A00%3A00%2B08%3A00/17/defect-7/template",
                },
                {
                    "image_id": "sample-1_defective",
                    "image_type": "defective",
                    "role": "patch_defective",
                    "content_type": "image/png",
                    "filename": "defective.png",
                    "access_url": "/api/v1/sc/images/2026-08-29T08%3A00%3A00%2B08%3A00/17/defect-7/defective",
                },
                {
                    "image_id": "sample-1_difference",
                    "image_type": "difference",
                    "role": "patch_difference",
                    "content_type": "image/png",
                    "filename": "difference.png",
                    "access_url": "/api/v1/sc/images/2026-08-29T08%3A00%3A00%2B08%3A00/17/defect-7/difference",
                },
            ],
            "label": "scratch",
        }
    ]
