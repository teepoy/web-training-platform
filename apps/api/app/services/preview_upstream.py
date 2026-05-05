from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.domain.preview import PreviewItem, PreviewPage


class UpstreamAdapter(ABC):
    @abstractmethod
    async def resolve_collection(self, collection_ref: str) -> dict[str, Any]: ...

    @abstractmethod
    async def fetch_page(self, collection_ref: str, cursor: str | None, limit: int) -> PreviewPage: ...

    @abstractmethod
    async def estimate_total(self, collection_ref: str) -> int | None: ...


class MockUpstreamAdapter(UpstreamAdapter):
    """Deterministic mock upstream adapter for preview sessions."""

    TOTAL = 50

    async def resolve_collection(self, collection_ref: str) -> dict[str, Any]:
        if not collection_ref.strip():
            raise ValueError("collection_ref must not be empty")
        return {"collection_ref": collection_ref, "type": "mock"}

    async def fetch_page(self, collection_ref: str, cursor: str | None, limit: int) -> PreviewPage:
        offset = int(cursor) if cursor else 0
        items: list[PreviewItem] = []
        for i in range(offset, min(offset + limit, self.TOTAL)):
            items.append(
                PreviewItem(
                    upstream_item_id=f"{collection_ref}-{i}",
                    image_uris=[f"https://picsum.photos/seed/{collection_ref}-{i}/400/300"],
                    metadata={"index": i, "collection": collection_ref},
                )
            )
        next_offset = offset + len(items)
        has_more = next_offset < self.TOTAL
        return PreviewPage(
            items=items,
            next_cursor=str(next_offset) if has_more else None,
            has_more=has_more,
            estimated_total=self.TOTAL,
        )

    async def estimate_total(self, collection_ref: str) -> int | None:
        return self.TOTAL
