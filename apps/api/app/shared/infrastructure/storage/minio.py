from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
import re
from io import BytesIO

from minio.commonconfig import Filter
from minio.lifecycleconfig import (
    Expiration,
    LifecycleConfig,
    Rule,
)
from minio import Minio

from app.core.config import AppConfig

_S3_URI_RE = re.compile(r"^s3://([^/]+)/(.+)$")
EXPORT_LIFECYCLE_RULE_ID = "finetune-export-expiration"
_LEGACY_EXPORT_MULTIPART_ABORT_RULE_ID = "finetune-export-multipart-abort"


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse an s3:// URI into (bucket, object_name)."""
    m = _S3_URI_RE.match(uri)
    if not m:
        raise ValueError(f"Invalid s3 URI: {uri!r}")
    return m.group(1), m.group(2)


@dataclass(frozen=True)
class MinioExportLifecycle:
    prefix: str
    expiration_days: int

    def __post_init__(self) -> None:
        if not self.prefix:
            raise ValueError("export lifecycle prefix must be non-empty")
        if self.expiration_days <= 0:
            raise ValueError("export lifecycle expiration_days must be positive")

    def to_rules(self) -> list[Rule]:
        # MinIO applies expiration days to complete objects and abandoned
        # multipart uploads in unversioned buckets. It intentionally does not
        # persist the S3 AbortIncompleteMultipartUpload field, so emitting that
        # field would make strict read-after-write validation impossible.
        return [
            Rule(
                status="Enabled",
                rule_filter=Filter(prefix=self.prefix),
                rule_id=EXPORT_LIFECYCLE_RULE_ID,
                expiration=Expiration(days=self.expiration_days),
            )
        ]


def build_minio_export_lifecycle(cfg: AppConfig) -> MinioExportLifecycle | None:
    exports_cfg = cfg.storage.minio.lifecycle.exports
    if not exports_cfg.enabled:
        return None
    return MinioExportLifecycle(
        prefix=str(exports_cfg.prefix),
        expiration_days=int(exports_cfg.expiration_days),
    )


class MinioArtifactStorage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        export_lifecycle: MinioExportLifecycle | None = None,
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
        self.export_lifecycle = export_lifecycle

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
            client.put_object(
                bucket_name=bucket,
                object_name=object_name,
                data=BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

        await asyncio.to_thread(_put)
        return f"s3://{self.bucket}/{object_name}"

    async def put_file(
        self,
        object_name: str,
        path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        bucket = self.bucket
        client = self.client

        def _put() -> None:
            client.fput_object(
                bucket_name=bucket,
                object_name=object_name,
                file_path=path,
                content_type=content_type,
            )

        await asyncio.to_thread(_put)
        return f"s3://{bucket}/{object_name}"

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

        def _get() -> bytes:
            response = client.get_object(bucket_name=bucket, object_name=object_name)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:
            raise FileNotFoundError(
                f"Object not found in MinIO bucket={bucket!r}: {uri!r}"
            ) from exc

    async def get_file(self, uri: str, destination: str) -> None:
        if not uri.startswith("s3://"):
            raise FileNotFoundError(f"Unsupported URI scheme: {uri!r}")
        bucket, object_name = _parse_s3_uri(uri)
        try:
            await asyncio.to_thread(
                self.client.fget_object,
                bucket,
                object_name,
                destination,
            )
        except Exception as exc:
            raise FileNotFoundError(
                f"Object not found in MinIO bucket={bucket!r}: {uri!r}"
            ) from exc

    async def get_size(self, uri: str) -> int:
        if not uri.startswith("s3://"):
            raise FileNotFoundError(f"Unsupported URI scheme: {uri!r}")
        bucket, object_name = _parse_s3_uri(uri)
        try:
            stat = await asyncio.to_thread(
                self.client.stat_object,
                bucket,
                object_name,
            )
        except Exception as exc:
            raise FileNotFoundError(
                f"Object not found in MinIO bucket={bucket!r}: {uri!r}"
            ) from exc
        size = getattr(stat, "size", None)
        if not isinstance(size, int) or size < 0:
            raise RuntimeError(f"MinIO returned an invalid object size for {uri!r}")
        return size

    async def iter_bytes(
        self,
        uri: str,
        *,
        offset: int = 0,
        length: int | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        if not uri.startswith("s3://"):
            raise FileNotFoundError(f"Unsupported URI scheme: {uri!r}")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if length is not None and length < 0:
            raise ValueError("length must be non-negative")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        bucket, object_name = _parse_s3_uri(uri)
        response = await asyncio.to_thread(
            self.client.get_object,
            bucket,
            object_name,
            offset,
            length or 0,
        )
        remaining = length
        try:
            while remaining is None or remaining > 0:
                read_size = (
                    chunk_size if remaining is None else min(chunk_size, remaining)
                )
                chunk = await asyncio.to_thread(response.read, read_size)
                if not chunk:
                    break
                yield chunk
                if remaining is not None:
                    remaining -= len(chunk)
        finally:
            await asyncio.to_thread(response.close)
            await asyncio.to_thread(response.release_conn)

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


def prepare_minio_storage(
    client: Minio,
    *,
    artifact_bucket: str,
    runtime_bucket: str,
    export_lifecycle: MinioExportLifecycle | None,
) -> None:
    """Create API-owned buckets and converge the managed export lifecycle."""
    for bucket in (artifact_bucket, runtime_bucket):
        if not client.bucket_exists(bucket):
            try:
                client.make_bucket(bucket)
            except Exception:
                if not client.bucket_exists(bucket):
                    raise

    if export_lifecycle is not None:
        existing = _existing_lifecycle_rules(client, artifact_bucket)
        unmanaged = [rule for rule in existing if not _is_managed_rule(rule)]
        client.set_bucket_lifecycle(
            artifact_bucket,
            LifecycleConfig([*unmanaged, *export_lifecycle.to_rules()]),
        )

    validate_minio_storage(
        client,
        artifact_bucket=artifact_bucket,
        runtime_bucket=runtime_bucket,
        export_lifecycle=export_lifecycle,
    )


def validate_minio_storage(
    client: Minio,
    *,
    artifact_bucket: str,
    runtime_bucket: str,
    export_lifecycle: MinioExportLifecycle | None,
) -> None:
    """Verify API-owned buckets and managed lifecycle rules without mutation."""
    missing = [
        bucket
        for bucket in (artifact_bucket, runtime_bucket)
        if not client.bucket_exists(bucket)
    ]
    if missing:
        raise RuntimeError(f"Required MinIO buckets are missing: {', '.join(missing)}")
    if export_lifecycle is None:
        return

    actual = {
        str(rule.rule_id): _lifecycle_rule_signature(rule)
        for rule in _existing_lifecycle_rules(client, artifact_bucket)
        if _is_managed_rule(rule)
    }
    expected = {
        str(rule.rule_id): _lifecycle_rule_signature(rule)
        for rule in export_lifecycle.to_rules()
    }
    if actual != expected:
        raise RuntimeError(
            f"MinIO lifecycle mismatch for bucket {artifact_bucket!r}: "
            f"expected managed rules {sorted(expected)}, got {sorted(actual)}"
        )


def _existing_lifecycle_rules(client: Minio, bucket: str) -> list[Rule]:
    try:
        lifecycle = client.get_bucket_lifecycle(bucket)
    except Exception as exc:
        if getattr(exc, "code", None) == "NoSuchLifecycleConfiguration":
            return []
        raise
    if lifecycle is None:
        return []
    return list(lifecycle.rules)


def _is_managed_rule(rule: Rule) -> bool:
    return str(rule.rule_id) in {
        EXPORT_LIFECYCLE_RULE_ID,
        _LEGACY_EXPORT_MULTIPART_ABORT_RULE_ID,
    }


def _lifecycle_rule_signature(rule: Rule) -> tuple[object, ...]:
    rule_filter = rule.rule_filter
    expiration = rule.expiration
    multipart_abort = rule.abort_incomplete_multipart_upload
    return (
        rule.status,
        rule_filter.prefix if rule_filter is not None else None,
        expiration.days if expiration is not None else None,
        multipart_abort.days_after_initiation if multipart_abort is not None else None,
    )
