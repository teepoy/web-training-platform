from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
from io import BytesIO
from typing import Any

from minio.commonconfig import Filter
from minio.lifecycleconfig import (
    AbortIncompleteMultipartUpload,
    Expiration,
    LifecycleConfig,
    Rule,
)
from minio import Minio

_S3_URI_RE = re.compile(r"^s3://([^/]+)/(.+)$")
_EXPORT_LIFECYCLE_RULE_ID = "finetune-export-expiration"
_EXPORT_MULTIPART_ABORT_RULE_ID = "finetune-export-multipart-abort"
logger = logging.getLogger(__name__)


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
    abort_incomplete_multipart_upload_days: int | None = None

    def __post_init__(self) -> None:
        if not self.prefix:
            raise ValueError("export lifecycle prefix must be non-empty")
        if self.expiration_days <= 0:
            raise ValueError("export lifecycle expiration_days must be positive")
        if (
            self.abort_incomplete_multipart_upload_days is not None
            and self.abort_incomplete_multipart_upload_days <= 0
        ):
            raise ValueError(
                "export lifecycle abort_incomplete_multipart_upload_days "
                "must be positive"
            )

    def to_rules(self) -> list[Rule]:
        rules = [
            Rule(
                status="Enabled",
                rule_filter=Filter(prefix=self.prefix),
                rule_id=_EXPORT_LIFECYCLE_RULE_ID,
                expiration=Expiration(days=self.expiration_days),
            )
        ]
        if self.abort_incomplete_multipart_upload_days is not None:
            rules.append(
                Rule(
                    status="Enabled",
                    rule_filter=Filter(prefix=self.prefix),
                    rule_id=_EXPORT_MULTIPART_ABORT_RULE_ID,
                    abort_incomplete_multipart_upload=(
                        AbortIncompleteMultipartUpload(
                            days_after_initiation=(
                                self.abort_incomplete_multipart_upload_days
                            )
                        )
                    ),
                )
            )
        return rules


def build_minio_export_lifecycle(cfg: Any) -> MinioExportLifecycle | None:
    lifecycle_cfg = cfg.storage.minio.get("lifecycle")
    if lifecycle_cfg is None:
        return None
    exports_cfg = lifecycle_cfg.get("exports")
    if exports_cfg is None or not bool(exports_cfg.get("enabled", False)):
        return None
    return MinioExportLifecycle(
        prefix=str(exports_cfg.prefix),
        expiration_days=int(exports_cfg.expiration_days),
        abort_incomplete_multipart_upload_days=int(
            exports_cfg.abort_incomplete_multipart_upload_days
        )
        if exports_cfg.get("abort_incomplete_multipart_upload_days") is not None
        else None,
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
        self._lifecycle_configured_buckets: set[str] = set()

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
            self._ensure_export_lifecycle(bucket)
            client.put_object(
                bucket_name=bucket,
                object_name=object_name,
                data=BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

        await asyncio.to_thread(_put)
        return f"s3://{self.bucket}/{object_name}"

    def _ensure_export_lifecycle(self, bucket: str) -> None:
        config = self.export_lifecycle
        if config is None or bucket in self._lifecycle_configured_buckets:
            return

        rules = self._existing_lifecycle_rules(bucket)
        rules = [
            rule
            for rule in rules
            if rule.rule_id
            not in {_EXPORT_LIFECYCLE_RULE_ID, _EXPORT_MULTIPART_ABORT_RULE_ID}
        ]
        rules.extend(config.to_rules())
        try:
            self.client.set_bucket_lifecycle(bucket, LifecycleConfig(rules))
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code != "InvalidArgument":
                raise
            logger.warning(
                "Skipping MinIO lifecycle configuration for bucket %s: %s",
                bucket,
                exc,
            )
        self._lifecycle_configured_buckets.add(bucket)

    def _existing_lifecycle_rules(self, bucket: str) -> list[Rule]:
        try:
            lifecycle = self.client.get_bucket_lifecycle(bucket)
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == "NoSuchLifecycleConfiguration":
                return []
            raise
        if lifecycle is None:
            return []
        return list(lifecycle.rules)

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
