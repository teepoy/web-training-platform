from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ScImportStatus(BaseModel):
    status: Literal["pending", "running", "completed", "failed"]
    dataset_id: str = ""
    dataset_name: str = ""
    source_inspection_time: str = ""
    source_wafer_key: int = 0
    storage_mode: str = "file_shard_sparse"
    imported_count: int = 0
    remaining_count: int = 0
    error: str | None = None
