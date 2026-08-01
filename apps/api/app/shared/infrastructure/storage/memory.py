from __future__ import annotations

import asyncio
from pathlib import Path


class InMemoryArtifactStorage:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        self._objects[object_name] = data
        return f"memory://{object_name}"

    async def get_bytes(self, uri: str) -> bytes:
        # uri format: memory://{object_name}
        prefix = "memory://"
        if not uri.startswith(prefix):
            raise FileNotFoundError(f"Unknown URI scheme: {uri!r}")
        object_name = uri[len(prefix) :]
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
        data = await self.get_bytes(uri)
        await asyncio.to_thread(Path(destination).write_bytes, data)

    async def delete(self, uri: str) -> None:
        prefix = "memory://"
        if not uri.startswith(prefix):
            raise FileNotFoundError(f"Unknown URI scheme: {uri!r}")
        object_name = uri[len(prefix) :]
        if object_name not in self._objects:
            raise FileNotFoundError(f"Object not found in memory storage: {uri!r}")
        del self._objects[object_name]

    async def list_prefix(self, prefix: str) -> list[str]:
        return [f"memory://{name}" for name in self._objects if name.startswith(prefix)]
