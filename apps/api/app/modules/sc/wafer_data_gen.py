"""Shared wafer demo data generation.

Single source of truth for wafer coordinate generation, class digit
images, and PatchSample construction.  Used by:

* ``libs/seedmaker/.../wafer_demo.py`` — seedmaker dataset seeding
* ``apps/api/.../sc/adapter/_wafer_mock/mock_store.py`` — mock upstream reader
* ``scripts/smoke_wafer_e2e.py`` — smoke test labels / constants
"""

from __future__ import annotations

import base64
import io
import math
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

# Smoke-test labels (first 10 class digits mapped to defect names for training)
LABELS: dict[int, str] = {
    0: "Scratch",
    1: "Particle",
    2: "Pattern Defect",
    3: "Residue",
    4: "Crack",
    5: "Void",
    6: "Bridge",
    7: "Protrusion",
    8: "Contamination",
    9: "Missing",
}

# ── Pre-generated class images (one 32×32 patch + one 224×224 review) ──

_patch_images: dict[int, str] = {}
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


def _make_digit_image(size: int, text: str) -> str:
    """Create a PNG data URI with *text* centred on a dark background."""
    img = Image.new("RGB", (size, size), color=(28, 28, 30))
    draw = ImageDraw.Draw(img)
    font = _get_font(max(size // 3, 12))
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2
    y = (size - th) // 2
    draw.text((x, y), text, fill=(220, 220, 220), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _init_class_images() -> None:
    for cls_idx in range(NUM_CLASSES):
        digit = str(cls_idx)
        _patch_images[cls_idx] = _make_digit_image(32, digit)
        _review_images[cls_idx] = _make_digit_image(224, digit)


_init_class_images()


# ── Public API ─────────────────────────────────────────────────────────


def patch_image_for_class(class_idx: int) -> str:
    """Return the 32×32 patch image data URI for *class_idx*."""
    return _patch_images[class_idx % NUM_CLASSES]


def review_image_for_class(class_idx: int) -> str:
    """Return the 224×224 review image data URI for *class_idx*."""
    return _review_images[class_idx % NUM_CLASSES]


def wafer_coordinates(sample_idx: int, *, seed: int = RANDOM_SEED) -> tuple[int, int]:
    """Uniform-area wafer coordinates (nanometers) inside the wafer disk."""
    rng = random.Random(seed + sample_idx)
    r = WAFER_RADIUS_NM * math.sqrt(rng.random())
    theta = rng.random() * 2 * math.pi
    return int(r * math.cos(theta)), int(r * math.sin(theta))


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
            ShardImageRef(image_id=_patch_images[class_idx], role="patch_template"),
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
