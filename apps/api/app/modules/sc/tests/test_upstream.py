"""Comprehensive feature tests for SC upstream module.

Covers:
- TestSampleProjection: from_sample_to_patch_sample() + mapper view projection
"""

from __future__ import annotations

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
# TestClass: TestSampleProjection
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
        assert result.inspection_time == "2024-01-15T08:30:00+08:00"
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
        assert result.inspection_time == "2024-01-15T08:30:00+08:00"
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
