"""Tests for sparse training record schema and assembler."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.sc.app.services.sparse_training_records import (
    SparseTrainingRecord,
    SparseTrainingRecordAssembler,
)
from app.shared.api.schemas import Annotation
from platform_runtime.sparse import (
    DatasetManifest,
    SampleLocator,
    ShardEntry,
    SparseManifestReader,
)
from platform_runtime.sparse.store import DatasetPayloadStore


def _annotation(sample_id: str, label: str) -> Annotation:
    return Annotation(sample_id=sample_id, label=label, created_by="tester")


def _locator(dataset_id: str, shard_idx: int, row_idx: int) -> SampleLocator:
    return SampleLocator(
        dataset_id=dataset_id,
        shard_index=shard_idx,
        row_index=row_idx,
        upstream_item_id=f"D{row_idx + 1:03d}",
    )


def _make_manifest(
    dataset_id: str,
    *,
    shard_count: int = 1,
    row_counts: list[int] | None = None,
    sample_index: dict[str, SampleLocator] | None = None,
) -> DatasetManifest:
    if row_counts is None:
        row_counts = [10] * shard_count
    shards = [
        ShardEntry(
            shard_index=i,
            uri=f"s3://bucket/shards/{i:06d}.parquet",
            row_count=rc,
            checksum_sha256="abc",
            byte_size=100,
        )
        for i, rc in enumerate(row_counts)
    ]
    return DatasetManifest(
        dataset_id=dataset_id,
        storage_mode="file_shard_sparse",
        shard_count=shard_count,
        total_rows=sum(row_counts),
        shards=shards,
        sample_index=sample_index or {},
    )


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestSparseTrainingRecordModel:
    def test_defaults_fill_empty_strings_and_dict(self):
        record = SparseTrainingRecord(sample_id="D001", label="defect")
        assert record.sample_id == "D001"
        assert record.label == "defect"
        assert record.image_uri == ""
        assert record.defective_uri == ""
        assert record.reference_uri == ""
        assert record.metadata == {}

    def test_full_record_construction(self):
        record = SparseTrainingRecord(
            sample_id="D001",
            label="defect",
            image_uri="http://img.com/d001.png",
            defective_uri="http://img.com/defect_d001.png",
            reference_uri="http://img.com/template.png",
            metadata={"review_images": [{"image_url": "x"}]},
        )
        assert record.image_uri == "http://img.com/d001.png"
        assert record.defective_uri == "http://img.com/defect_d001.png"
        assert record.reference_uri == "http://img.com/template.png"
        assert record.metadata["review_images"][0]["image_url"] == "x"

    def test_json_roundtrip(self):
        record = SparseTrainingRecord(
            sample_id="D001",
            label="defect",
            defective_uri="http://img.com/defect.png",
        )
        raw = record.model_dump_json()
        restored = SparseTrainingRecord.model_validate_json(raw)
        assert restored.defective_uri == "http://img.com/defect.png"
        assert restored.label == "defect"


# ---------------------------------------------------------------------------
# Assembler tests (mock-based)
# ---------------------------------------------------------------------------

_DS = "ds-sparse-test"
_ORG = "org-1"
_SHARD_URI = "s3://bucket/shards/000000.parquet"


@pytest.fixture
def mock_storage() -> MagicMock:
    stg = MagicMock()
    stg.get_bytes = AsyncMock()
    return stg


@pytest.fixture
def mock_manifest_reader() -> MagicMock:
    reader = MagicMock(spec=SparseManifestReader)
    reader.read_row_batch = AsyncMock()
    return reader


@pytest.fixture
def mock_payload_store() -> MagicMock:
    store = MagicMock(spec=DatasetPayloadStore)
    store.get_manifest = AsyncMock()
    return store


@pytest.fixture
def assembler(mock_manifest_reader, mock_payload_store) -> SparseTrainingRecordAssembler:
    return SparseTrainingRecordAssembler(
        manifest_reader=mock_manifest_reader,
        payload_store=mock_payload_store,
    )


class TestSparseTrainingRecordAssembler:
    def test_assemble_zero_annotations_returns_empty(
        self, assembler, mock_storage, mock_payload_store
    ):
        records = _run_assemble(assembler, [], mock_storage, mock_payload_store)
        assert records == []
        mock_payload_store.get_manifest.assert_not_called()

    def test_assemble_manifest_not_found(
        self, assembler, mock_storage, mock_payload_store
    ):
        mock_payload_store.get_manifest.side_effect = FileNotFoundError()
        annotations = [_annotation("D001", "defect")]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)
        assert records == []

    def test_assemble_manifest_general_error(
        self, assembler, mock_storage, mock_payload_store
    ):
        mock_payload_store.get_manifest.side_effect = RuntimeError("oops")
        annotations = [_annotation("D001", "defect")]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)
        assert records == []

    def test_assemble_empty_sample_index(
        self, assembler, mock_storage, mock_payload_store
    ):
        manifest = _make_manifest(_DS, sample_index={})
        mock_payload_store.get_manifest.return_value = manifest
        annotations = [_annotation("D001", "defect")]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)
        assert records == []

    def test_assemble_no_matching_index_entries(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        manifest = _make_manifest(
            _DS,
            sample_index={
                "D001": _locator(_DS, 0, 0),
            },
        )
        mock_payload_store.get_manifest.return_value = manifest
        annotations = [_annotation("D999", "defect")]  # not in index
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)
        assert records == []
        mock_manifest_reader.read_row_batch.assert_not_called()

    def test_assemble_single_shard_single_annotation(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        manifest = _make_manifest(
            _DS,
            shard_count=1,
            row_counts=[3],
            sample_index={
                "D001": _locator(_DS, 0, 0),
            },
        )
        mock_payload_store.get_manifest.return_value = manifest
        _setup_shard_rows(
            mock_manifest_reader,
            [
                {"sample_id": "D001", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D002", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D003", "image_uris": "[]", "metadata": "{}"},
            ],
        )

        annotations = [_annotation("D001", "defect")]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)

        assert len(records) == 1
        assert records[0].sample_id == "D001"
        assert records[0].label == "defect"

    def test_assemble_multiple_annotations_one_shard(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        manifest = _make_manifest(
            _DS,
            shard_count=1,
            row_counts=[5],
            sample_index={
                "D001": _locator(_DS, 0, 0),
                "D003": _locator(_DS, 0, 2),
                "D005": _locator(_DS, 0, 4),
            },
        )
        mock_payload_store.get_manifest.return_value = manifest
        _setup_shard_rows(
            mock_manifest_reader,
            [
                {"sample_id": "D001", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D002", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D003", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D004", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D005", "image_uris": "[]", "metadata": "{}"},
            ],
        )

        annotations = [
            _annotation("D001", "defect"),
            _annotation("D003", "clean"),
            _annotation("D005", "crack"),
        ]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)

        assert len(records) == 3
        labels = {r.sample_id: r.label for r in records}
        assert labels == {"D001": "defect", "D003": "clean", "D005": "crack"}

    def test_assemble_multiple_shards(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        manifest = _make_manifest(
            _DS,
            shard_count=2,
            row_counts=[3, 3],
            sample_index={
                "D001": _locator(_DS, 0, 0),
                "D004": _locator(_DS, 1, 0),
                "D006": _locator(_DS, 1, 2),
            },
        )
        mock_payload_store.get_manifest.return_value = manifest
        _setup_shard_rows(
            mock_manifest_reader,
            [
                {"sample_id": "D001", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D002", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D003", "image_uris": "[]", "metadata": "{}"},
            ],
            shard_uri="s3://bucket/shards/000000.parquet",
        )
        _setup_shard_rows(
            mock_manifest_reader,
            [
                {"sample_id": "D004", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D005", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D006", "image_uris": "[]", "metadata": "{}"},
            ],
            shard_uri="s3://bucket/shards/000001.parquet",
        )

        annotations = [
            _annotation("D001", "defect"),
            _annotation("D004", "clean"),
            _annotation("D006", "crack"),
        ]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)

        assert len(records) == 3
        assert {r.sample_id for r in records} == {"D001", "D004", "D006"}

    def test_row_index_out_of_range_skipped(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        manifest = _make_manifest(
            _DS,
            shard_count=1,
            row_counts=[2],
            sample_index={
                "D001": _locator(_DS, 0, 5),  # out of range
            },
        )
        mock_payload_store.get_manifest.return_value = manifest
        _setup_shard_rows(
            mock_manifest_reader,
            [
                {"sample_id": "D001", "image_uris": "[]", "metadata": "{}"},
                {"sample_id": "D002", "image_uris": "[]", "metadata": "{}"},
            ],
        )

        annotations = [_annotation("D001", "defect")]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)
        assert records == []

    def test_column_projection_requests_only_training_columns(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        manifest = _make_manifest(
            _DS,
            sample_index={"D001": _locator(_DS, 0, 0)},
        )
        mock_payload_store.get_manifest.return_value = manifest
        _setup_shard_rows(
            mock_manifest_reader,
            [{"sample_id": "D001", "image_uris": "[]", "metadata": "{}"}],
        )

        annotations = [_annotation("D001", "defect")]
        _run_assemble(assembler, annotations, mock_storage, mock_payload_store)

        call_kwargs = mock_manifest_reader.read_row_batch.call_args.kwargs
        assert call_kwargs["columns"] == ["sample_id", "image_uris", "metadata"]

    def test_uris_extracted_from_json_columns(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        image_uris_json = json.dumps(["http://img.com/review_1.png"])
        metadata_json = json.dumps(
            {
                "review_images": [
                    {
                        "image_url": "http://img.com/defect.png",
                        "image_name": "defect.png",
                        "image_id": 1,
                        "image_type": "review",
                    }
                ],
                "patch_images": {
                    "template": {"image_url": "http://img.com/template.png"}
                },
            }
        )
        manifest = _make_manifest(
            _DS,
            sample_index={"D001": _locator(_DS, 0, 0)},
        )
        mock_payload_store.get_manifest.return_value = manifest
        _setup_shard_rows(
            mock_manifest_reader,
            [{"sample_id": "D001", "image_uris": image_uris_json, "metadata": metadata_json}],
        )

        annotations = [_annotation("D001", "defect")]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)

        assert len(records) == 1
        r = records[0]
        assert r.image_uri == "http://img.com/review_1.png"
        assert r.defective_uri == "http://img.com/defect.png"
        assert r.reference_uri == "http://img.com/template.png"
        assert r.metadata["review_images"][0]["image_url"] == "http://img.com/defect.png"

    def test_empty_uri_columns_graceful(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        manifest = _make_manifest(
            _DS,
            sample_index={"D001": _locator(_DS, 0, 0)},
        )
        mock_payload_store.get_manifest.return_value = manifest
        _setup_shard_rows(
            mock_manifest_reader,
            [{"sample_id": "D001", "image_uris": "", "metadata": ""}],
        )

        annotations = [_annotation("D001", "defect")]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)

        assert len(records) == 1
        r = records[0]
        assert r.image_uri == ""
        assert r.defective_uri == ""
        assert r.reference_uri == ""

    def test_invalid_json_in_columns_does_not_crash(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        manifest = _make_manifest(
            _DS,
            sample_index={"D001": _locator(_DS, 0, 0)},
        )
        mock_payload_store.get_manifest.return_value = manifest
        _setup_shard_rows(
            mock_manifest_reader,
            [{"sample_id": "D001", "image_uris": "not-valid-json", "metadata": "{{bad}}"}],
        )

        annotations = [_annotation("D001", "defect")]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)

        assert len(records) == 1
        r = records[0]
        assert r.sample_id == "D001"
        assert r.label == "defect"

    def test_partial_annotation_match_returns_only_matched(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        manifest = _make_manifest(
            _DS,
            sample_index={"D001": _locator(_DS, 0, 0)},
        )
        mock_payload_store.get_manifest.return_value = manifest
        _setup_shard_rows(
            mock_manifest_reader,
            [{"sample_id": "D001", "image_uris": "[]", "metadata": "{}"}],
        )

        annotations = [
            _annotation("D001", "defect"),
            _annotation("D999", "clean"),  # not in index
        ]
        records = _run_assemble(assembler, annotations, mock_storage, mock_payload_store)
        assert len(records) == 1
        assert records[0].sample_id == "D001"

    def test_shard_read_is_called_once_per_shard(
        self, assembler, mock_storage, mock_payload_store, mock_manifest_reader
    ):
        manifest = _make_manifest(
            _DS,
            shard_count=1,
            row_counts=[10],
            sample_index={
                "D001": _locator(_DS, 0, 0),
                "D005": _locator(_DS, 0, 4),
                "D009": _locator(_DS, 0, 8),
            },
        )
        mock_payload_store.get_manifest.return_value = manifest
        _setup_shard_rows(
            mock_manifest_reader,
            [
                {"sample_id": f"D{i + 1:03d}", "image_uris": "[]", "metadata": "{}"}
                for i in range(10)
            ],
        )

        annotations = [
            _annotation("D001", "defect"),
            _annotation("D005", "clean"),
            _annotation("D009", "crack"),
        ]
        _run_assemble(assembler, annotations, mock_storage, mock_payload_store)

        assert mock_manifest_reader.read_row_batch.call_count == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_shard_rows(
    mock_reader: MagicMock,
    rows: list[dict[str, object]],
    shard_uri: str = _SHARD_URI,
) -> None:
    existing = getattr(mock_reader, "_row_map", None)
    if existing is None:
        existing = {}
        mock_reader._row_map = existing

        async def _return_rows(*args, **kwargs):
            uri = kwargs.get("shard_uri")
            if uri is not None and uri in mock_reader._row_map:
                return list(mock_reader._row_map[uri])
            return []

        mock_reader.read_row_batch.side_effect = _return_rows

    existing[shard_uri] = list(rows)


def _run_assemble(
    assembler: SparseTrainingRecordAssembler,
    annotations: list[Annotation],
    storage: MagicMock,
    payload_store: MagicMock,
) -> list[SparseTrainingRecord]:
    import asyncio

    return asyncio.run(
        assembler.assemble(
            dataset_id=_DS,
            org_id=_ORG,
            annotations=annotations,
            storage=storage,
        )
    )
