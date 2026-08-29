from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path


class InMemoryArtifactStorage:
    """Process-local object storage for tests; never wired by production code."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        del content_type
        self._objects[object_name] = data
        return f"memory://{object_name}"

    async def get_bytes(self, uri: str) -> bytes:
        object_name = self._object_name(uri)
        if object_name not in self._objects:
            raise FileNotFoundError(f"Object not found in memory storage: {uri!r}")
        return self._objects[object_name]

    async def put_file(
        self,
        object_name: str,
        path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        del content_type
        self._objects[object_name] = await asyncio.to_thread(Path(path).read_bytes)
        return f"memory://{object_name}"

    async def get_file(self, uri: str, destination: str) -> None:
        await asyncio.to_thread(
            Path(destination).write_bytes, await self.get_bytes(uri)
        )

    async def get_size(self, uri: str) -> int:
        return len(await self.get_bytes(uri))

    async def iter_bytes(
        self,
        uri: str,
        *,
        offset: int = 0,
        length: int | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if length is not None and length < 0:
            raise ValueError("length must be non-negative")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        data = await self.get_bytes(uri)
        end = len(data) if length is None else min(len(data), offset + length)
        for position in range(offset, end, chunk_size):
            yield data[position : min(position + chunk_size, end)]

    async def delete(self, uri: str) -> None:
        object_name = self._object_name(uri)
        if object_name not in self._objects:
            raise FileNotFoundError(f"Object not found in memory storage: {uri!r}")
        del self._objects[object_name]

    async def list_prefix(self, prefix: str) -> list[str]:
        return [f"memory://{name}" for name in self._objects if name.startswith(prefix)]

    @staticmethod
    def _object_name(uri: str) -> str:
        prefix = "memory://"
        if not uri.startswith(prefix):
            raise FileNotFoundError(f"Unknown URI scheme: {uri!r}")
        return uri[len(prefix) :]
