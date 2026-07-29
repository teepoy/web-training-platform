"""Shared wafer demo data generation.

Single source of truth for wafer coordinate generation, class digit
images, and PatchSample construction.  Used by:

* ``scripts/seedmaker/datasets/wafer_demo.py`` — dev/test dataset seeding
* ``apps/api/.../sc/adapter/_wafer_mock/mock_store.py`` — mock upstream reader
* ``scripts/smoke_wafer_e2e.py`` — smoke test labels / constants
"""

from __future__ import annotations

import base64
import io
import random
import sys
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

from app.modules.sc.models import PatchSample, ReviewImage, ShardImageRef

# ── Constants ──────────────────────────────────────────────────────────

NUM_CLASSES: int = 100
WAFER_RADIUS_NM: int = 150_000_000
SAMPLES_PER_WAFER: int = 100_000
RANDOM_SEED: int = 42
DIE_SIZE_X_NM: int = 8_000_000
DIE_SIZE_Y_NM: int = 5_000_000
DIE_RANGE: int = 3
DIE_CORNER_FRACTION: float = 0.3

# Labels use the same numeric class identity as ``class_number``. Display names
# are a presentation concern and must not change persisted color-map keys.
LABELS: dict[int, str] = {
    class_number: str(class_number) for class_number in range(NUM_CLASSES)
}

# ── Pre-generated class images (one 32×32 patch + one 224×224 review) ──

_patch_images: dict[int, str] = {}
_defective_patch_images: dict[int, str] = {}
_review_images: dict[int, str] = {}


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths: list[str] = []
    if sys.platform == "darwin":
        paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
    else:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _make_digit_image(
    size: int,
    text: str,
    *,
    background: tuple[int, int, int] = (28, 28, 30),
    foreground: tuple[int, int, int] = (220, 220, 220),
) -> str:
    """Create a PNG data URI with *text* centred on a dark background."""
    img = Image.new("RGB", (size, size), color=background)
    draw = ImageDraw.Draw(img)
    font = _get_font(max(size // 3, 12))
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2
    y = (size - th) // 2
    draw.text((x, y), text, fill=foreground, font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _init_class_images() -> None:
    for cls_idx in range(NUM_CLASSES):
        digit = str(cls_idx)
        _patch_images[cls_idx] = _make_digit_image(32, digit)
        _defective_patch_images[cls_idx] = _make_digit_image(
            32,
            digit,
            background=(72, 24, 24),
            foreground=(255, 220, 160),
        )
        _review_images[cls_idx] = _make_digit_image(224, digit)


_init_class_images()


# ── Public API ─────────────────────────────────────────────────────────


def patch_image_for_class(class_idx: int) -> str:
    """Return the 32×32 patch image data URI for *class_idx*."""
    return _patch_images[class_idx % NUM_CLASSES]


def review_image_for_class(class_idx: int) -> str:
    """Return the 224×224 review image data URI for *class_idx*."""
    return _review_images[class_idx % NUM_CLASSES]


def defective_patch_image_for_class(class_idx: int) -> str:
    """Return the 32×32 defective patch image data URI for *class_idx*."""
    return _defective_patch_images[class_idx % NUM_CLASSES]


def wafer_coordinates(sample_idx: int, *, seed: int = RANDOM_SEED) -> tuple[int, int]:
    """Wafer coordinates (nanometers) in the lower-left corner of dies within
    +/- DIE_RANGE from the wafer center die grid.

    Picks a random die from the (2*DIE_RANGE+1)^2 grid centred at (0,0) and
    places the defect in the lower-left corner (first DIE_CORNER_FRACTION of
    the die in both X and Y).
    """
    rng = random.Random(seed + sample_idx)
    die_idx_x = rng.randint(-DIE_RANGE, DIE_RANGE)
    die_idx_y = rng.randint(-DIE_RANGE, DIE_RANGE)
    max_offset_x = int(DIE_SIZE_X_NM * DIE_CORNER_FRACTION)
    max_offset_y = int(DIE_SIZE_Y_NM * DIE_CORNER_FRACTION)
    offset_x = rng.randint(0, max_offset_x)
    offset_y = rng.randint(0, max_offset_y)
    wafer_x = die_idx_x * DIE_SIZE_X_NM + offset_x
    wafer_y = die_idx_y * DIE_SIZE_Y_NM + offset_y
    return wafer_x, wafer_y


def build_patch_sample(
    idx: int,
    *,
    inspection_time: datetime | None = None,
    wafer_key: int = 0,
    lot_id: str = "LOT-DEMO-001",
) -> PatchSample:
    """Build a single wafer demo PatchSample domain model.

    *class_number* = ``idx % NUM_CLASSES`` (the digit rendered on images).
    *rough_bin* = same as class_number.
    *inspection_time* is stamped on each sample (defaults to now if None).
    """
    class_idx = idx % NUM_CLASSES
    wx, wy = wafer_coordinates(idx)
    if inspection_time is None:
        inspection_time = datetime.now(timezone.utc)

    point_id = str(idx + 1)
    return PatchSample(
        sample_id=point_id,
        defect_id=str(idx + 1),
        inspection_time=inspection_time,
        wafer_key=wafer_key,
        lot_id=lot_id,
        wafer_x=wx,
        wafer_y=wy,
        rough_bin=class_idx,
        class_number=class_idx,
        shard_images=[
            ShardImageRef(
                image_id=_patch_images[class_idx],
                image_type="template",
                role="patch_template",
                content_type="image/png",
                filename="template.png",
            ),
            ShardImageRef(
                image_id=_defective_patch_images[class_idx],
                image_type="defective",
                role="patch_defective",
                content_type="image/png",
                filename="defective.png",
            ),
        ],
        review_images=[
            ReviewImage(
                image_url=_review_images[class_idx],
                image_name=f"review-{class_idx:02d}",
                image_id=idx + 1,
                image_type="REVIEW_HIGH_MAG",
            ),
        ],
    )
