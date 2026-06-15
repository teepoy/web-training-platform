"""Unit tests for ScImportRequest and ScImportResponse schemas.

Covers:
- Valid ScImportRequest construction with all fields
- Default storage_mode value
- Invalid storage_mode raises ValidationError
- Empty dataset_name raises ValidationError
- ScImportResponse default values
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.sc.schemas import ScImportRequest, ScImportResponse


class TestScImportRequest:
    """Tests for ScImportRequest schema."""

    def test_valid_request_all_fields(self) -> None:
        """All fields explicitly set should match."""
        req = ScImportRequest(
            source_inspection_time="2024-01-15T08:30:00",
            source_wafer_key=1,
            dataset_name="Test",
            storage_mode="file_shard_sparse",
            filters={"wafer_id": "W001"},
            label_space=["defect"],
        )
        assert req.source_inspection_time == "2024-01-15T08:30:00"
        assert req.source_wafer_key == 1
        assert req.dataset_name == "Test"
        assert req.storage_mode == "file_shard_sparse"
        assert req.filters == {"wafer_id": "W001"}
        assert req.label_space == ["defect"]

    def test_default_storage_mode(self) -> None:
        """storage_mode should default to 'file_shard_sparse' when omitted."""
        req = ScImportRequest(
            source_inspection_time="2024-01-15T08:30:00",
            source_wafer_key=1,
            dataset_name="Test",
        )
        assert req.storage_mode == "file_shard_sparse"

    def test_invalid_storage_mode_raises_validation_error(self) -> None:
        """storage_mode='invalid' should raise ValidationError."""
        with pytest.raises(ValidationError):
            ScImportRequest(
                source_inspection_time="2024-01-15T08:30:00",
                source_wafer_key=1,
                dataset_name="Test",
                storage_mode="invalid",
            )

    def test_empty_dataset_name_raises_validation_error(self) -> None:
        """dataset_name='' should raise ValidationError due to min_length=1."""
        with pytest.raises(ValidationError):
            ScImportRequest(
                source_inspection_time="2024-01-15T08:30:00",
                source_wafer_key=1,
                dataset_name="",
            )


class TestScImportResponse:
    """Tests for ScImportResponse schema."""

    def test_default_values(self) -> None:
        """ScImportResponse defaults should be correct when only required fields given."""
        resp = ScImportResponse(
            status="completed",
        )
        assert resp.status == "completed"
        assert resp.dataset_id == ""
        assert resp.imported_count == 0
        assert resp.error is None
