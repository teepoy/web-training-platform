from __future__ import annotations

import base64
import io
import json
import zipfile
from typing import Any

try:
    import boto3  # type: ignore[import-untyped]
except ImportError:
    boto3 = None

from app.domain.preview import PreviewItem, PreviewPage
from app.services.preview_upstream import UpstreamAdapter


class S3ZipPreviewUpstream(UpstreamAdapter):
    """Preview upstream that reads seed-generated zip archives from S3/MinIO.

    Option B: in-memory zip cache with on-demand extraction.

    Collection ref format: ``{bucket}/{prefix}``
    (the ``s3:`` scheme is stripped by ``PreviewUpstreamRouter``).

    Example collection_ref: ``finetune-preview/seed/mock-multi-image``
      → bucket = ``finetune-preview``, prefix = ``seed/mock-multi-image``

    Each collection corresponds to a seed output (index.json + chunk zips).
    Index and zip cache are per-collection, bounded by LRU eviction.

    Perf profile:
    - First page: download 1-2 zips → ~0.5s (localhost MinIO)
    - Same-chunk pages: cache hit → instant
    - Cross-chunk pages: download new zip → latency again
    - Memory: max 10 zips × ~8 MB per collection = ~80 MB

    NOTE: boto3 ``get_object`` is synchronous. In production with high
    concurrency, consider ``aioboto3`` or ``run_in_executor``.
    """

    def __init__(
        self,
        *,
        endpoint_url: str = "http://localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        region: str = "us-east-1",
        max_cached_zips: int = 10,
    ) -> None:
        if boto3 is None:
            raise ImportError("boto3 is required for S3ZipPreviewUpstream")
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._max_cached = max_cached_zips
        self._indexes: dict[str, list[dict]] = {}
        self._zip_caches: dict[str, dict[str, bytes]] = {}
        self._access_orders: dict[str, list[str]] = {}

    @staticmethod
    def _parse_ref(collection_ref: str) -> tuple[str, str]:
        if "/" not in collection_ref:
            raise ValueError(
                f"Invalid S3 collection_ref: '{collection_ref}'. "
                f"Expected format: 'bucket/prefix'"
            )
        bucket, prefix = collection_ref.split("/", 1)
        return bucket, prefix.rstrip("/")

    async def resolve_collection(self, collection_ref: str) -> dict[str, Any]:
        if not collection_ref.strip():
            raise ValueError("collection_ref must not be empty")
        bucket, prefix = self._parse_ref(collection_ref)
        index = await self._load_index(bucket, prefix)
        total = sum(e.get("sample_count", 0) for e in index)
        return {
            "collection_ref": collection_ref,
            "type": "s3-zip",
            "bucket": bucket,
            "prefix": prefix,
            "chunks": len(index),
            "estimated_total": total,
        }

    async def fetch_page(
        self, collection_ref: str, cursor: str | None, limit: int
    ) -> PreviewPage:
        bucket, prefix = self._parse_ref(collection_ref)
        index = await self._load_index(bucket, prefix)
        cursor_int = int(cursor) if cursor else 0
        total_samples = sum(e.get("sample_count", 0) for e in index)

        items: list[PreviewItem] = []
        remaining = limit
        current_pos = cursor_int

        for entry in index:
            start, end = entry.get("sample_range", [0, 0])
            if current_pos > end:
                continue
            if remaining <= 0:
                break

            chunk_key = entry.get("chunk", "")
            if not chunk_key:
                continue

            zip_bytes = await self._get_zip(bucket, collection_ref, chunk_key)
            chunk_items = self._extract_chunk(zip_bytes, current_pos, start, remaining)
            items.extend(chunk_items)
            remaining -= len(chunk_items)
            current_pos = start + len(chunk_items) if chunk_items else end + 1

        has_more = current_pos < total_samples
        return PreviewPage(
            items=items,
            next_cursor=str(current_pos) if has_more else None,
            has_more=has_more,
            estimated_total=total_samples,
        )

    async def estimate_total(self, collection_ref: str) -> int | None:
        bucket, prefix = self._parse_ref(collection_ref)
        index = await self._load_index(bucket, prefix)
        return sum(e.get("sample_count", 0) for e in index)

    async def _load_index(self, bucket: str, prefix: str) -> list[dict]:
        cache_key = f"{bucket}/{prefix}"
        if cache_key in self._indexes:
            return self._indexes[cache_key]
        resp = self._s3.get_object(
            Bucket=bucket,
            Key=f"{prefix}/index.json",
        )
        self._indexes[cache_key] = json.loads(resp["Body"].read())
        return self._indexes[cache_key]

    async def _get_zip(self, bucket: str, cache_key: str, chunk_key: str) -> bytes:
        if cache_key not in self._zip_caches:
            self._zip_caches[cache_key] = {}
            self._access_orders[cache_key] = []
        zips = self._zip_caches[cache_key]
        order = self._access_orders[cache_key]

        if chunk_key not in zips:
            resp = self._s3.get_object(Bucket=bucket, Key=chunk_key)
            zips[chunk_key] = resp["Body"].read()
            order.append(chunk_key)
            while len(zips) > self._max_cached:
                old = order.pop(0)
                del zips[old]
        return zips[chunk_key]

    def _extract_chunk(
        self, zip_bytes: bytes, cursor: int, chunk_start: int, limit: int,
    ) -> list[PreviewItem]:
        items: list[PreviewItem] = []
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            manifest_data = json.loads(zf.read("manifest.json"))
            for m in manifest_data:
                sid = int(m.get("id", "0"))
                if sid < cursor:
                    continue
                if len(items) >= limit:
                    break

                image_uris: list[str] = []
                for img_name in m.get("images", []):
                    raw = zf.read(img_name)
                    b64 = base64.b64encode(raw).decode()
                    ext = img_name.rsplit(".", 1)[-1].lower() if "." in img_name else "bin"
                    mime = "png" if ext == "png" else "jpeg"
                    image_uris.append(f"data:image/{mime};base64,{b64}")

                items.append(PreviewItem(
                    upstream_item_id=str(m["id"]),
                    image_uris=image_uris,
                    metadata=m.get("metadata", {}),
                ))
        return items
