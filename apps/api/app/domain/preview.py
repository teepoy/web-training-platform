from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


class PreviewItem(BaseModel):
    upstream_item_id: str
    image_uris: list[str]
    metadata: dict[str, object] = Field(default_factory=dict)


class PreviewPage(BaseModel):
    items: list[PreviewItem]
    next_cursor: str | None
    has_more: bool
    estimated_total: int | None


PreviewPersistScope = Literal["entire_collection", "loaded_items_only"]


class PreviewPersistStatus(BaseModel):
    dataset_id: str
    persist_session_id: str
    status: Literal["pending", "running", "completed", "failed"]
    imported_count: int = 0
    remaining_count: int = 0
    error: str | None = None


@dataclass
class PreviewSession:
    session_id: str
    collection_ref: str
    user_id: str
    items: list[PreviewItem] = field(default_factory=list)
    next_cursor: str | None = None
    estimated_total: int | None = None
    persist_lock: bool = False
    persist_status: PreviewPersistStatus | None = None
    created_at: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_active = time.monotonic()

    def can_start_persist(self) -> bool:
        return not self.persist_lock

    def start_persist(self) -> bool:
        """Idempotent. Returns True only the first time."""
        if self.persist_lock:
            return False
        self.persist_lock = True
        return True
