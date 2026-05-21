from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CreatePreviewSessionRequest(BaseModel):
    collection_ref: str


class PreviewItemResponse(BaseModel):
    upstream_item_id: str
    image_uris: list[str]
    metadata: dict[str, Any] = {}


class PreviewSessionResponse(BaseModel):
    session_id: str
    collection_ref: str
    classification_enabled: bool
    estimated_total: int | None
    loaded_count: int
    next_cursor: str | None
    has_more: bool


class PreviewItemsResponse(BaseModel):
    items: list[PreviewItemResponse]
    next_cursor: str | None
    has_more: bool
    estimated_total: int | None


class StartPersistRequest(BaseModel):
    scope: str = "entire_collection"


class PersistStatusResponse(BaseModel):
    dataset_id: str
    persist_session_id: str
    status: str
    imported_count: int
    remaining_count: int
    error: str | None
