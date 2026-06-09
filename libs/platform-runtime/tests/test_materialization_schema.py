"""RED tests: view-generic runtime materialization schema contracts.

These tests MUST FAIL because ``RuntimeMaterializationManifest`` and
``RuntimeMaterializedRow`` do not exist yet. They define the contract
shape that must be implemented in
``libs/platform-runtime/src/platform_runtime/sparse/models.py``.
"""

from __future__ import annotations

from datetime import datetime

import pytest

try:
    from platform_runtime.sparse.models import (
        RuntimeMaterializationManifest,
        RuntimeMaterializedRow,
        ShardEntry,
    )

    _HAVE_MODELS = True
except ImportError:
    _HAVE_MODELS = False
    RuntimeMaterializationManifest = None
    RuntimeMaterializedRow = None
    ShardEntry = None


def test_runtime_models_exist() -> None:
    """Fail until RuntimeMaterializationManifest and RuntimeMaterializedRow exist."""
    if not _HAVE_MODELS:
        pytest.fail(
            "RuntimeMaterializationManifest / RuntimeMaterializedRow not found. "
            "Implement them in …/platform_runtime/sparse/models.py"
        )


@pytest.mark.skipif(not _HAVE_MODELS, reason="Models not implemented yet")
class TestRuntimeMaterializationManifest:
    """RuntimeMaterializationManifest contract shape."""

    def test_manifest_has_all_required_fields(self) -> None:
        """All contract fields must be present and typed correctly."""
        assert RuntimeMaterializationManifest is not None
        assert ShardEntry is not None
        manifest = RuntimeMaterializationManifest(
            purpose="train",
            job_id="job-001",
            org_id="org-42",
            dataset_id="ds-7",
            view_id="patch_image_v1",
            schema_version="1.0",
            row_count=100,
            byte_count=2048000,
            shards=[
                ShardEntry(
                    shard_index=0,
                    uri="s3://bucket/shard-0.parquet",
                    row_count=100,
                    format="parquet",
                    checksum_sha256="abc123",
                    byte_size=2048000,
                ),
            ],
        )
        assert manifest.purpose == "train"
        assert manifest.job_id == "job-001"
        assert manifest.org_id == "org-42"
        assert manifest.dataset_id == "ds-7"
        assert manifest.view_id == "patch_image_v1"
        assert manifest.schema_version == "1.0"
        assert manifest.row_count == 100
        assert manifest.byte_count == 2048000
        assert len(manifest.shards) == 1
        assert isinstance(manifest.created_at, datetime)

    def test_manifest_supports_predict_purpose(self) -> None:
        """Purpose field must accept predict as well as train."""
        assert RuntimeMaterializationManifest is not None
        manifest = RuntimeMaterializationManifest(
            purpose="predict",
            job_id="job-002",
            org_id="org-42",
            dataset_id="ds-8",
            view_id="patch_image_v1",
            schema_version="1.0",
            row_count=50,
            byte_count=1024000,
        )
        assert manifest.purpose == "predict"

    def test_manifest_rejects_invalid_purpose(self) -> None:
        """Purpose must be constrained to train/predict."""
        assert RuntimeMaterializationManifest is not None
        with pytest.raises(ValueError, match="purpose|Purpose"):
            RuntimeMaterializationManifest(
                purpose="embed",  # pyright: ignore[reportArgumentType]
                job_id="job-003",
                org_id="org-42",
                dataset_id="ds-9",
                view_id="patch_image_v1",
                schema_version="1.0",
                row_count=0,
                byte_count=0,
            )


@pytest.mark.skipif(not _HAVE_MODELS, reason="Models not implemented yet")
class TestRuntimeMaterializedRow:
    """RuntimeMaterializedRow contract shape."""

    def test_row_has_minimum_fields(self) -> None:
        """Row must have sample_id, nullable label, and at least one bytes field."""
        assert RuntimeMaterializedRow is not None
        row = RuntimeMaterializedRow(
            sample_id="s-1",
            label="defective",
            defective_bytes=b"fake_defective",
            reference_bytes=b"fake_reference",
        )
        assert row.sample_id == "s-1"
        assert row.label == "defective"
        assert row.defective_bytes == b"fake_defective"
        assert row.reference_bytes == b"fake_reference"

    def test_row_label_nullable(self) -> None:
        """Label must accept None for unlabeled inference / prediction."""
        assert RuntimeMaterializedRow is not None
        row = RuntimeMaterializedRow(
            sample_id="s-2",
            label=None,
            defective_bytes=b"fake_defective",
        )
        assert row.label is None

    def test_row_dual_image_view_columns(self) -> None:
        """patch_image_v1 dual-image view must carry defective_bytes and reference_bytes."""
        assert RuntimeMaterializedRow is not None
        row = RuntimeMaterializedRow(
            sample_id="s-3",
            label="good",
            defective_bytes=b"defective_data",
            reference_bytes=b"reference_data",
        )
        assert row.defective_bytes == b"defective_data"
        assert row.reference_bytes == b"reference_data"

    def test_row_rejects_uri_only(self) -> None:
        """Rows with only URI references and no embedded bytes must be rejected."""
        assert RuntimeMaterializedRow is not None
        with pytest.raises((ValueError, TypeError), match="bytes|Bytes|required"):
            RuntimeMaterializedRow(
                sample_id="s-4",
                label="defective",
            )

    def test_rejects_trainer_specific_payload(self) -> None:
        """Trainer-specific payloads (e.g. ClipEmbeddingPayload) must not
        pass as RuntimeMaterializedRow."""
        assert RuntimeMaterializedRow is not None
        with pytest.raises((ValueError, TypeError)):
            RuntimeMaterializedRow(  # pyright: ignore[reportCallIssue]
                embeddings=[0.1, 0.2, 0.3],  # pyright: ignore[reportCallIssue]
                model_id="clip-vit-base-patch32",  # pyright: ignore[reportCallIssue]
            )
