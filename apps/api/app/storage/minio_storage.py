from __future__ import annotations

import asyncio
from io import BytesIO

from minio import Minio


class MinioArtifactStorage:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool = False) -> None:
        self.client = Minio(endpoint=endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self.bucket = bucket

    async def put_bytes(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        bucket = self.bucket
        client = self.client

        def _put() -> None:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            client.put_object(
                bucket_name=bucket,
                object_name=object_name,
                data=BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

        await asyncio.to_thread(_put)
        return f"s3://{self.bucket}/{object_name}"

    async def get_bytes(self, uri: str) -> bytes:
        # uri format: s3://{bucket}/{object_name}
        prefix = f"s3://{self.bucket}/"
        if not uri.startswith(prefix):
            raise FileNotFoundError(f"URI does not match bucket: {uri!r}")
        object_name = uri[len(prefix):]
        client = self.client
        bucket = self.bucket
        try:
            return await asyncio.to_thread(
                lambda: client.get_object(bucket_name=bucket, object_name=object_name).read()
            )
        except Exception as exc:
            raise FileNotFoundError(f"Object not found in MinIO: {uri!r}") from exc


class InMemoryArtifactStorage:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put_bytes(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._objects[object_name] = data
        return f"memory://{object_name}"

    async def get_bytes(self, uri: str) -> bytes:
        # uri format: memory://{object_name}
        prefix = "memory://"
        if not uri.startswith(prefix):
            raise FileNotFoundError(f"Unknown URI scheme: {uri!r}")
        object_name = uri[len(prefix):]
        if object_name not in self._objects:
            raise FileNotFoundError(f"Object not found in memory storage: {uri!r}")
        return self._objects[object_name]
