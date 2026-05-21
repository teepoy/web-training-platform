from __future__ import annotations


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

    async def delete(self, uri: str) -> None:
        """Delete an object from in-memory storage."""
        prefix = "memory://"
        if not uri.startswith(prefix):
            raise FileNotFoundError(f"Unknown URI scheme: {uri!r}")
        object_name = uri[len(prefix) :]
        if object_name not in self._objects:
            raise FileNotFoundError(f"Object not found in memory storage: {uri!r}")
        del self._objects[object_name]
