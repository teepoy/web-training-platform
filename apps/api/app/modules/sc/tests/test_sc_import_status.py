from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.sc.domain.entities.sc_import import ScImportStatus


class TestScImportStatus:
    """ScImportStatus domain entity — TDD RED→GREEN→REFACTOR."""

    def test_valid_status_literals(self) -> None:
        """All four valid status values are accepted."""
        for status in ("pending", "running", "completed", "failed"):
            s = ScImportStatus(status=status, dataset_id="ds-1")
            assert s.status == status

    def test_defaults_are_correct(self) -> None:
        """Default values: imported_count=0, remaining_count=0, error=None."""
        s = ScImportStatus(status="pending", dataset_id="ds-1")

        assert s.imported_count == 0
        assert s.remaining_count == 0
        assert s.error is None
        assert s.dataset_id == "ds-1"

    def test_invalid_status_raises_validation_error(self) -> None:
        """An unknown status literal raises pydantic.ValidationError."""
        with pytest.raises(ValidationError):
            ScImportStatus(status="unknown", dataset_id="ds-1")  # pyright: ignore[reportArgumentType]

    def test_model_dump_json_serializable(self) -> None:
        """model_dump(mode='json') produces correct JSON-serializable dict."""
        s = ScImportStatus(
            status="running",
            dataset_id="ds-42",
            imported_count=5,
            remaining_count=95,
            error=None,
        )
        dumped = s.model_dump(mode="json")
        assert dumped == {
            "status": "running",
            "dataset_id": "ds-42",
            "dataset_name": "",
            "source_inspection_time": "",
            "source_wafer_key": 0,
            "storage_mode": "file_shard_sparse",
            "imported_count": 5,
            "remaining_count": 95,
            "error": None,
        }
