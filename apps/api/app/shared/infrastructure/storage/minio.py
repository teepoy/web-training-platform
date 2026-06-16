from __future__ import annotations

import asyncio
import re
from io import BytesIO

from minio import Minio

_S3_URI_RE = re.compile(r"^s3://([^/]+)/(.+)$")


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse an s3:// URI into (bucket, object_name)."""
    m = _S3_URI_RE.match(uri)
    if not m:
        raise ValueError(f"Invalid s3 URI: {uri!r}")
    return m.group(1), m.group(2)


class MinioArtifactStorage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.bucket = bucket
        self.secure = secure

    def polars_storage_options(self) -> dict[str, str]:
        """Return cloud options accepted by Polars' native object-store reader."""
        scheme = "https" if self.secure else "http"
        options = {
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "aws_endpoint_url": f"{scheme}://{self.endpoint}",
            "aws_region": "us-east-1",
        }
        if not self.secure:
            options["aws_allow_http"] = "true"
        return options

    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
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
        """Read bytes from a MinIO object identified by an ``s3://`` URI.

        Handles both the configured default bucket and *cross-bucket* URIs
        (e.g. ``s3://review-images/...``).  This is needed because shard
        metadata may reference images stored in buckets other than the
        primary artifact bucket.
        """
        if not uri.startswith("s3://"):
            raise FileNotFoundError(f"Unsupported URI scheme: {uri!r}")

        bucket, object_name = _parse_s3_uri(uri)
        client = self.client
        try:
            return await asyncio.to_thread(
                lambda: client.get_object(
                    bucket_name=bucket, object_name=object_name
                ).read()
            )
        except Exception as exc:
            raise FileNotFoundError(
                f"Object not found in MinIO bucket={bucket!r}: {uri!r}"
            ) from exc

    async def delete(self, uri: str) -> None:
        """Delete an object from MinIO storage identified by an ``s3://`` URI."""
        if not uri.startswith("s3://"):
            raise FileNotFoundError(f"Unsupported URI scheme: {uri!r}")

        bucket, object_name = _parse_s3_uri(uri)
        client = self.client
        try:
            await asyncio.to_thread(
                lambda: client.remove_object(
                    bucket_name=bucket, object_name=object_name
                )
            )
        except Exception as exc:
            raise FileNotFoundError(
                f"Failed to delete object from MinIO: {uri!r}"
            ) from exc

    async def list_prefix(self, prefix: str) -> list[str]:
        client = self.client
        bucket = self.bucket

        def _list() -> list[str]:
            return [
                f"s3://{bucket}/{obj.object_name}"
                for obj in client.list_objects(
                    bucket_name=bucket, prefix=prefix, recursive=True
                )
                if obj.object_name
            ]

        return await asyncio.to_thread(_list)
