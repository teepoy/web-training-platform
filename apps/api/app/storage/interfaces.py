from __future__ import annotations

from typing import Protocol


class ArtifactStorage(Protocol):
    async def put_bytes(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Store bytes and return the URI."""
        ...

    async def get_bytes(self, uri: str) -> bytes:
        """Retrieve bytes from the given URI."""
        ...

    async def delete(self, uri: str) -> None:
        """Delete the object at the given URI."""
        ...
