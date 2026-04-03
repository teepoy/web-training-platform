from __future__ import annotations

from typing import Protocol


class ArtifactStorage(Protocol):
    async def put_bytes(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
