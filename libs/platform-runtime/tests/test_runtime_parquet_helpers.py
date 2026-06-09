"""RED tests for runtime parquet writer/reader helpers.

These tests will fail because the helpers (``platform_runtime.sparse.parquet_helpers``)
don't exist yet. They serve as a specification for the expected API.

``write_runtime_parquet(rows, schema_version, *, row_group_size, metadata) -> bytes``
``read_runtime_parquet(data, *, expected_schema_version) -> tuple[list[dict], dict]``
"""

from __future__ import annotations

import pytest


def _import_helpers():
    """Import the (not-yet-implemented) parquet helpers.

    This will raise ``ModuleNotFoundError`` until the module is created.
    Each test calls this so the error is a test **failure**, not a
    collection error.
    """
    from platform_runtime.sparse.parquet_helpers import (
        read_runtime_parquet,
        write_runtime_parquet,
    )

    return write_runtime_parquet, read_runtime_parquet


def test_embedded_bytes_roundtrip():
    """Write a row with binary ``image_bytes``, read it back, verify exact match."""
    write_runtime_parquet, read_runtime_parquet = _import_helpers()

    rows = [
        {"sample_id": "s1", "image_bytes": b"abc123", "label": "class-A"},
    ]
    data = write_runtime_parquet(rows, schema_version="1.0")
    result_rows, metadata = read_runtime_parquet(data)

    assert len(result_rows) == 1
    row = result_rows[0]
    assert row["sample_id"] == "s1"
    assert isinstance(row["image_bytes"], bytes)
    assert row["image_bytes"] == b"abc123"
    assert row["label"] == "class-A"


def test_schema_version_mismatch_raises():
    """Reading a parquet written with schema_version=2.0 while expecting 1.0
    should raise a clear ``ValueError`` (not silently corrupt data)."""
    write_runtime_parquet, read_runtime_parquet = _import_helpers()

    rows = [{"sample_id": "s1", "image_bytes": b"abc", "label": "x"}]
    data = write_runtime_parquet(rows, schema_version="2.0")

    with pytest.raises(ValueError, match="(?i)schema.versi"):
        read_runtime_parquet(data, expected_schema_version="1.0")


def test_row_group_boundary_preserves_rows():
    """5 rows written with ``row_group_size=2`` (-> 3 row groups) must all
    survive a round-trip with exact field values."""
    write_runtime_parquet, read_runtime_parquet = _import_helpers()

    rows = [
        {
            "sample_id": f"s{i}",
            "image_bytes": b"data" + bytes([i]),
            "label": f"class-{i}",
        }
        for i in range(5)
    ]
    data = write_runtime_parquet(rows, schema_version="1.0", row_group_size=2)
    result_rows, metadata = read_runtime_parquet(data)

    assert len(result_rows) == 5
    for i, expected in enumerate(rows):
        actual = result_rows[i]
        assert actual["sample_id"] == expected["sample_id"]
        assert actual["image_bytes"] == expected["image_bytes"]
        assert actual["label"] == expected["label"]


def test_manifest_metadata_roundtrip():
    """Manifest metadata (purpose, job_id, view_id, schema_version, row_count,
    byte_count) written alongside the parquet must be returned verbatim."""
    write_runtime_parquet, read_runtime_parquet = _import_helpers()

    rows = [{"sample_id": "s1", "image_bytes": b"abc", "label": "x"}]
    manifest = {
        "purpose": "training",
        "job_id": "job-123",
        "view_id": "view-456",
        "schema_version": "1.0",
        "row_count": 1,
        "byte_count": 3,
    }
    data = write_runtime_parquet(rows, schema_version="1.0", metadata=manifest)
    result_rows, metadata = read_runtime_parquet(data)

    assert metadata.get("purpose") == "training"
    assert metadata.get("job_id") == "job-123"
    assert metadata.get("view_id") == "view-456"
    assert metadata.get("schema_version") == "1.0"
    assert metadata.get("row_count") == 1
    assert metadata.get("byte_count") == 3


def test_writer_populates_checksum_and_byte_size():
    """After writing, the manifest must contain ``checksum_sha256`` and
    ``byte_size`` fields populated by the writer."""
    write_runtime_parquet, read_runtime_parquet = _import_helpers()

    rows = [{"sample_id": "s1", "image_bytes": b"hello", "label": "x"}]
    data = write_runtime_parquet(rows, schema_version="1.0")
    _, metadata = read_runtime_parquet(data)

    assert "checksum_sha256" in metadata, (
        "writer must populate checksum_sha256 in manifest metadata"
    )
    assert isinstance(metadata["checksum_sha256"], str)
    assert len(metadata["checksum_sha256"]) == 64

    assert "byte_size" in metadata, (
        "writer must populate byte_size in manifest metadata"
    )
    assert isinstance(metadata["byte_size"], int)
    assert metadata["byte_size"] > 0
