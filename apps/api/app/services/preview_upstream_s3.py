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
    """Preview upstream that reads from S3-hosted zip archives.

    Option B: in-memory zip cache with on-demand extraction.
    Downloads zip files from S3/MinIO on first access, caches raw bytes
    in memory (LRU), and extracts images from zip on demand.

    Designed to work with zips produced by ``S3ZipWriter`` from seed_maker.
    Each zip contains a ``manifest.json`` and individual PNG/JPEG image files
    for up to 500 samples.

    Perf profile:
    - First page: download 1-2 zips → ~0.5s (localhost MinIO)
    - Same-chunk pages: cache hit → instant
    - Cross-chunk pages: download new zip → latency again
    - Memory: max 10 zips × ~8 MB = ~80 MB

    NOTE: boto3 ``get_object`` is synchronous. In production with high
    concurrency, consider ``aioboto3`` or ``run_in_executor`` to avoid
    blocking the event loop. Acceptable for dev/testing.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str,
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
        self._bucket = bucket
        self._prefix = prefix.rstrip("/")
        self._max_cached = max_cached_zips
        self._index: list[dict] | None = None
        self._zip_cache: dict[str, bytes] = {}
        self._access_order: list[str] = []

    async def resolve_collection(self, collection_ref: str) -> dict[str, Any]:
        if not collection_ref.strip():
            raise ValueError("collection_ref must not be empty")
        index = await self._load_index()
        total = sum(e.get("sample_count", 0) for e in index)
        return {
            "collection_ref": collection_ref,
            "type": "s3-zip",
            "bucket": self._bucket,
            "prefix": self._prefix,
            "chunks": len(index),
            "estimated_total": total,
        }

    async def fetch_page(
        self, collection_ref: str, cursor: str | None, limit: int
    ) -> PreviewPage:
        index = await self._load_index()
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

            zip_bytes = await self._get_zip(chunk_key)
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
        index = await self._load_index()
        return sum(e.get("sample_count", 0) for e in index)

    async def _load_index(self) -> list[dict]:
        if self._index is not None:
            return self._index
        resp = self._s3.get_object(
            Bucket=self._bucket,
            Key=f"{self._prefix}/index.json",
        )
        self._index = json.loads(resp["Body"].read())
        return self._index

    async def _get_zip(self, chunk_key: str) -> bytes:
        if chunk_key not in self._zip_cache:
            resp = self._s3.get_object(
                Bucket=self._bucket,
                Key=chunk_key,
            )
            data = resp["Body"].read()
            self._zip_cache[chunk_key] = data
            self._access_order.append(chunk_key)
            while len(self._zip_cache) > self._max_cached:
                old = self._access_order.pop(0)
                del self._zip_cache[old]
        return self._zip_cache[chunk_key]

    def _extract_chunk(
        self,
        zip_bytes: bytes,
        cursor: int,
        chunk_start: int,
        limit: int,
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
                    upstream_item_id=f"{self._prefix}-{m['id']}",
                    image_uris=image_uris,
                    metadata=m.get("metadata", {}),
                ))
        return items
