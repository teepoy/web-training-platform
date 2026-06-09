"""Comprehensive feature tests for SC upstream module.

Covers:
- TestPatchImageCache: disk cache with TTL, lock dedup, eviction
- TestPresignedUrlCache: in-memory URL cache
- TestSampleProjection: from_sample_to_patch_sample() + mapper view projection
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

import pytest

from app.modules.sc.adapter._wafer_mock.cache import CacheFetchError, PatchImageCache
from app.modules.sc.adapter._wafer_mock.url_cache import PresignedUrlCache
from app.modules.sc.domain.mapper import (
    from_sample_to_patch_sample,
    patch_sample_to_sample,
    patch_sample_to_patch_image_v1,
    patch_sample_to_review_image_v1,
)
from app.modules.sc.models import (
    PatchSample,
    ReviewImage,
    ShardImageRef,
)
from app.core.mapper_registry import mapper


# ═══════════════════════════════════════════════════════════════════════
# TestClass 1: TestPatchImageCache
# ═══════════════════════════════════════════════════════════════════════


class TestPatchImageCache:
    """Disk-based image cache: hit, miss, TTL, dedup, eviction, poison."""

    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        """Seed cache file, get_image -> returns bytes, no fetcher call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PatchImageCache(cache_dir=tmpdir, ttl_seconds=60)
            key = cache._cache_key("2024-01-15T08:30:00", 1, "D001", "template")
            cache._cache_path(key).write_bytes(b"cached image data")

            call_count = 0

            def mock_fetcher() -> bytes:
                nonlocal call_count
                call_count += 1
                return b"should not be called"

            data = await cache.get_image(
                "2024-01-15T08:30:00",
                1,
                "D001",
                "template",
                fetcher=mock_fetcher,
            )
            assert data == b"cached image data"
            assert call_count == 0
            cache.clear()

    @pytest.mark.asyncio
    async def test_cache_miss_no_fetcher(self) -> None:
        """Empty cache, get_image without fetcher -> CacheFetchError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PatchImageCache(cache_dir=tmpdir, ttl_seconds=60)
            with pytest.raises(CacheFetchError, match="no fetcher"):
                await cache.get_image(
                    "2024-01-15T08:30:00",
                    1,
                    "D001",
                    "template",
                )
            cache.clear()

    @pytest.mark.asyncio
    async def test_cache_miss_with_fetcher(self) -> None:
        """Empty cache, get_image with fetcher -> returns bytes, file created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PatchImageCache(cache_dir=tmpdir, ttl_seconds=60)
            call_count = 0

            def mock_fetcher() -> bytes:
                nonlocal call_count
                call_count += 1
                return b"fresh data"

            data = await cache.get_image(
                "2024-01-15T08:30:00",
                1,
                "D001",
                "template",
                fetcher=mock_fetcher,
            )
            assert data == b"fresh data"
            assert call_count == 1

            # Verify file was created on disk
            key = cache._cache_key("2024-01-15T08:30:00", 1, "D001", "template")
            assert cache._cache_path(key).exists()
            assert cache._cache_path(key).read_bytes() == b"fresh data"
            cache.clear()

    @pytest.mark.asyncio
    async def test_cache_ttl_expiry(self) -> None:
        """Seed with TTL=1s, get (hit), sleep 1.1s, get -> calls fetcher again."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PatchImageCache(cache_dir=tmpdir, ttl_seconds=1)
            call_count = 0

            def mock_fetcher() -> bytes:
                nonlocal call_count
                call_count += 1
                return b"re-fetched"

            # Seed via first fetch
            data1 = await cache.get_image(
                "2024-01-15T08:30:00",
                1,
                "D001",
                "template",
                fetcher=mock_fetcher,
            )
            assert data1 == b"re-fetched"
            assert call_count == 1

            # Immediate re-get should be a hit (fetcher not called again)
            data2 = await cache.get_image(
                "2024-01-15T08:30:00",
                1,
                "D001",
                "template",
                fetcher=mock_fetcher,
            )
            assert data2 == b"re-fetched"
            assert call_count == 1  # still 1

            # Wait for TTL to expire
            await asyncio.sleep(1.1)

            data3 = await cache.get_image(
                "2024-01-15T08:30:00",
                1,
                "D001",
                "template",
                fetcher=mock_fetcher,
            )
            assert data3 == b"re-fetched"
            assert call_count == 2  # fetcher called again
            cache.clear()

    @pytest.mark.asyncio
    async def test_cache_concurrent_dedup(self) -> None:
        """10 concurrent get_image for same key -> fetcher called exactly once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PatchImageCache(cache_dir=tmpdir, ttl_seconds=60)
            call_count = 0

            def mock_fetcher() -> bytes:
                nonlocal call_count
                call_count += 1
                time.sleep(0.05)
                return b"shared data"

            # 10 concurrent calls for the same key
            tasks = [
                cache.get_image(
                    "2024-01-15T08:30:00",
                    1,
                    "D001",
                    "template",
                    fetcher=mock_fetcher,
                )
                for _ in range(10)
            ]
            results = await asyncio.gather(*tasks)

            assert call_count == 1
            assert all(r == b"shared data" for r in results)
            cache.clear()

    @pytest.mark.asyncio
    async def test_cache_max_size_eviction(self) -> None:
        """Small max_size, write 3 files -> oldest evicted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Max size just enough for 1 file
            cache = PatchImageCache(
                cache_dir=tmpdir,
                ttl_seconds=600,
                max_size_bytes=512,
            )

            # Write file 1 (oldest)
            key1 = cache._cache_key("2024-01-15T08:30:00", 1, "D001", "template")
            cache._cache_path(key1).write_bytes(b"x" * 200)

            # Write file 2
            key2 = cache._cache_key("2024-02-20T14:00:00", 2, "D001", "template")
            cache._cache_path(key2).write_bytes(b"x" * 200)

            # Write file 3 -> should evict oldest (file 1)
            key3 = cache._cache_key("2024-03-10T22:15:00", 3, "D001", "template")
            cache._cache_path(key3).write_bytes(b"x" * 200)

            # Trigger eviction manually
            cache._evict_if_needed()

            # File 1 should be evicted (oldest), file 2 and 3 remain
            assert not cache._cache_path(key1).exists()
            assert cache._cache_path(key2).exists()
            assert cache._cache_path(key3).exists()
            cache.clear()

    @pytest.mark.asyncio
    async def test_cache_no_poison_on_failure(self) -> None:
        """Fetcher raises -> CacheFetchError, retry with good fetcher -> succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PatchImageCache(cache_dir=tmpdir, ttl_seconds=60)

            # First attempt: fetcher fails
            def bad_fetcher() -> bytes:
                raise RuntimeError("S3 is down")

            with pytest.raises(CacheFetchError, match="S3 is down"):
                await cache.get_image(
                    "2024-01-15T08:30:00",
                    1,
                    "D001",
                    "template",
                    fetcher=bad_fetcher,
                )

            # Second attempt: good fetcher should succeed
            def good_fetcher() -> bytes:
                return b"recovered"

            data = await cache.get_image(
                "2024-01-15T08:30:00",
                1,
                "D001",
                "template",
                fetcher=good_fetcher,
            )
            assert data == b"recovered"

            # Verify cache file now contains the good data
            key = cache._cache_key("2024-01-15T08:30:00", 1, "D001", "template")
            assert cache._cache_path(key).read_bytes() == b"recovered"
            cache.clear()

    @pytest.mark.asyncio
    async def test_cache_clear(self) -> None:
        """Seed files, clear() -> cache dir empty of non-tmp files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PatchImageCache(cache_dir=tmpdir, ttl_seconds=60)

            # Seed 3 files
            for i in range(3):
                key = cache._cache_key(
                    "2024-01-15T08:30:00", 1, f"D{i:03d}", "template"
                )
                cache._cache_path(key).write_bytes(b"data")

            # Count files before clear
            before = len(
                [
                    f
                    for f in Path(tmpdir).iterdir()
                    if f.is_file() and not f.name.endswith(".tmp")
                ]
            )
            assert before == 3

            cache.clear()

            after = len(
                [
                    f
                    for f in Path(tmpdir).iterdir()
                    if f.is_file() and not f.name.endswith(".tmp")
                ]
            )
            assert after == 0


# ═══════════════════════════════════════════════════════════════════════
# TestClass 2: TestPresignedUrlCache
# ═══════════════════════════════════════════════════════════════════════


class TestPresignedUrlCache:
    """In-memory presigned URL cache with TTL expiry."""

    def test_url_cache_hit(self) -> None:
        """get_or_generate with same key twice -> generator called once."""
        cache = PresignedUrlCache(ttl_seconds=600)
        call_count = 0

        def generator() -> str:
            nonlocal call_count
            call_count += 1
            return f"https://s3.example.com/presigned/{call_count}"

        url1 = cache.get_or_generate("key1", generator)
        assert call_count == 1
        assert url1 == "https://s3.example.com/presigned/1"

        url2 = cache.get_or_generate("key1", generator)
        assert call_count == 1  # not called again
        assert url2 == "https://s3.example.com/presigned/1"

    def test_url_cache_expiry(self) -> None:
        """get_or_generate after TTL -> generator called again."""
        cache = PresignedUrlCache(ttl_seconds=0)  # immediate expiry
        call_count = 0

        def generator() -> str:
            nonlocal call_count
            call_count += 1
            return f"https://s3.example.com/presigned/{call_count}"

        url1 = cache.get_or_generate("key1", generator)
        assert call_count == 1

        # TTL=0 means immediate expiry, so next call regenerates
        url2 = cache.get_or_generate("key1", generator)
        assert call_count == 2
        assert url2 != url1

    def test_url_cache_different_keys(self) -> None:
        """Different keys -> generator called for each."""
        cache = PresignedUrlCache(ttl_seconds=600)
        call_count = 0

        def generator() -> str:
            nonlocal call_count
            call_count += 1
            return f"https://s3.example.com/presigned/{call_count}"

        url_a = cache.get_or_generate("key_a", generator)
        assert call_count == 1

        url_b = cache.get_or_generate("key_b", generator)
        assert call_count == 2

        assert url_a != url_b


# ═══════════════════════════════════════════════════════════════════════
# TestClass 3: TestSampleProjection
# ═══════════════════════════════════════════════════════════════════════


class TestSampleProjection:
    """PatchSample view projection via the mapper registry."""

    def test_from_sample_patch_images(self) -> None:
        """Mapper parses metadata into patch-image fields."""
        raw = {
            "id": "s-abc",
            "metadata": {
                "inspection_time": "2024-01-15T08:30:00",
                "wafer_key": 1,
                "defect_id": "D001",
                "wafer_x": 23,
                "wafer_y": 45,
                "rough_bin": 1,
                "class_number": 5,
            },
        }

        sample = from_sample_to_patch_sample(raw)

        result = patch_sample_to_patch_image_v1(sample)
        assert result.sample_id == "s-abc"
        assert result.inspection_time == "2024-01-15T08:30:00"
        assert result.wafer_key == 1
        assert result.defect_id == "D001"
        assert result.wafer_x == 23
        assert result.wafer_y == 45

    def test_from_sample_review_images(self) -> None:
        """Mapper parses review_images from metadata into the review view."""
        raw = {
            "id": "s-review",
            "metadata": {
                "inspection_time": "2024-01-15T08:30:00",
                "wafer_key": 1,
                "defect_id": "D001",
                "wafer_x": 23,
                "wafer_y": 45,
                "rough_bin": 1,
                "review_images": [
                    {
                        "image_url": "http://ex.com/r1.png",
                        "image_name": "r1.png",
                        "image_id": 1,
                        "image_type": "review",
                    },
                ],
            },
        }

        sample = from_sample_to_patch_sample(raw)
        assert len(sample.review_images) == 1
        assert sample.review_images[0].image_id == 1

        result = patch_sample_to_review_image_v1(sample)
        assert result.sample_id == "s-review"
        assert result.inspection_time == "2024-01-15T08:30:00"
        assert result.wafer_key == 1
        assert len(result.review_images) == 1
        assert result.review_images[0]["image_id"] == 1

    def test_from_sample_sc_metadata_fields(self) -> None:
        """Mapper extracts SC-specific fields from metadata."""
        raw = {
            "id": "s-sc",
            "metadata": {
                "inspection_time": "2024-01-15T08:30:00",
                "wafer_key": 1,
                "defect_id": "D001",
                "lot_id": "LT-001",
                "wafer_x": 23,
                "wafer_y": 45,
                "rough_bin": 1,
                "class_number": 5,
            },
        }

        sample = from_sample_to_patch_sample(raw)
        assert sample.wafer_key == 1
        assert sample.defect_id == "D001"
        assert sample.lot_id == "LT-001"
        assert sample.wafer_x == 23
        assert sample.wafer_y == 45
        assert sample.rough_bin == 1
        assert sample.class_number == 5

    def test_get_adapter_dispatches_correctly(self) -> None:
        """The mapper registry returns the correct projection method for each view type."""
        sample = PatchSample(
            sample_id="s-dispatch",
            defect_id="D001",
            inspection_time=None,
        )

        assert mapper.get_mapper(PatchSample, "patch_image_v1") is patch_sample_to_patch_image_v1
        assert mapper.get_mapper(PatchSample, "review_image_v1") is patch_sample_to_review_image_v1

    def test_to_sample_from_sample_roundtrip(self) -> None:
        """Import and projection roundtrip preserves all SC fields."""
        from datetime import datetime, timezone
        from uuid import UUID

        original = PatchSample(
            sample_id="s-roundtrip",
            inspection_time=datetime(2024, 1, 15, 8, 30, tzinfo=timezone.utc),
            wafer_key=1,
            defect_id="D001",
            lot_id="LT-001",
            wafer_x=23,
            wafer_y=45,
            rough_bin=1,
            class_number=5,
            shard_images=[
                ShardImageRef(
                    image_id="img-1",
                    image_type="PATCH_TEMPLATE",
                    role="patch_template",
                ),
                ShardImageRef(
                    image_id="img-2",
                    image_type="PATCH_DEFECTIVE",
                    role="patch_defective",
                ),
            ],
            review_images=[
                ReviewImage(
                    image_url="http://r.png",
                    image_name="r.png",
                    image_id=1,
                    image_type="review",
                ),
            ],
        )

        sample = patch_sample_to_sample(original, dataset_id="ds-test-001")

        assert isinstance(UUID(sample.id), UUID)
        assert sample.id != original.sample_id
        assert sample.dataset_id == "ds-test-001"

        assert sample.metadata["sample_id"] == "s-roundtrip"
        assert sample.metadata["defect_id"] == "D001"
        assert sample.metadata["wafer_key"] == 1
        assert sample.metadata["lot_id"] == "LT-001"

        assert "img-1" in sample.image_uris
        assert "img-2" in sample.image_uris

        reconstructed = from_sample_to_patch_sample(sample)

        assert reconstructed.sample_id == original.sample_id
        assert reconstructed.inspection_time == original.inspection_time
        assert reconstructed.wafer_key == original.wafer_key
        assert reconstructed.defect_id == original.defect_id
        assert reconstructed.lot_id == original.lot_id
        assert reconstructed.wafer_x == original.wafer_x
        assert reconstructed.wafer_y == original.wafer_y
        assert reconstructed.rough_bin == original.rough_bin
        assert reconstructed.class_number == original.class_number
        assert reconstructed.review_images == original.review_images
        assert len(reconstructed.shard_images) == 2
        assert reconstructed.shard_images[0].image_id == "img-1"
