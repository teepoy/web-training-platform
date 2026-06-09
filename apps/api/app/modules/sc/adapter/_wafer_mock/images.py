from __future__ import annotations

import io
import random
import zipfile
from datetime import datetime
from typing import Protocol

_PATCH_SIZE = 32
_REVIEW_SIZE = 224

DEFAULT_PATCH_BUCKET = "sc-patch-images"
DEFAULT_REVIEW_BUCKET = "sc-review-images"


class _S3Client(Protocol):
    """Minimal Protocol for an S3-compatible client (e.g. boto3, minio).

    Only the methods used by wafer-mock image upload helpers are declared
    so that callers can pass any S3-compatible object without importing boto3.
    """

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> object: ...


class _Image(Protocol):
    """Minimal Protocol for a PIL-compatible Image object."""

    def save(self, buf: io.BytesIO, *, format: str, quality: int = 85) -> None: ...


def _ensure_pil() -> type:
    try:
        from PIL import Image as PILImageModule
    except ImportError:
        raise ImportError(
            "Pillow is required for image generation. Install with: pip install wafer-mock[s3]"
        )
    return PILImageModule


def generate_patch_image() -> _Image:
    """Generate a random 32x32 grayscale patch image."""
    pil = _ensure_pil()
    pixels = bytes(random.randint(0, 255) for _ in range(_PATCH_SIZE * _PATCH_SIZE))
    return pil.frombytes("L", (_PATCH_SIZE, _PATCH_SIZE), pixels)


def generate_review_image() -> _Image:
    """Generate a random 224x224 grayscale review image."""
    pil = _ensure_pil()
    pixels = bytes(random.randint(0, 255) for _ in range(_REVIEW_SIZE * _REVIEW_SIZE))
    return pil.frombytes("L", (_REVIEW_SIZE, _REVIEW_SIZE), pixels)


def generate_patch_image_bytes() -> tuple[bytes, str]:
    """Generate a random 32x32 grayscale patch image and return as PNG bytes.

    Returns:
        Tuple of (image_data, content_type).
    """
    img = generate_patch_image()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), "image/png"


def generate_review_image_bytes() -> tuple[bytes, str]:
    """Generate a random 224x224 grayscale review image and return as JPEG bytes.

    Returns:
        Tuple of (image_data, content_type).
    """
    img = generate_review_image()
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def _inspection_time_str(inspection_time: datetime) -> str:
    return inspection_time.strftime("%Y%m%d_%H%M%S")


def _defect_range_key(first: int, last: int) -> str:
    return f"{first:06d}-{last:06d}.zip"


def create_patch_zip(defect_ids: list[int]) -> bytes:
    """Create a zip archive of 32x32 patch PNGs for a batch of defects."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for defect_id in defect_ids:
            img = generate_patch_image()
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            zf.writestr(f"{defect_id:06d}.png", img_bytes.getvalue())
    return buf.getvalue()


def upload_patch_zips(
    s3_client: _S3Client,
    wafer_key: int,
    inspection_time: datetime,
    total_defects: int,
    batch_size: int = 500,
    patch_bucket: str = DEFAULT_PATCH_BUCKET,
) -> list[str]:
    """Upload patch image zips to S3 (patch_images bucket). Returns list of S3 keys."""
    keys: list[str] = []
    ts = _inspection_time_str(inspection_time)

    for start in range(1, total_defects + 1, batch_size):
        end = min(start + batch_size - 1, total_defects)
        defect_ids = list(range(start, end + 1))
        zip_data = create_patch_zip(defect_ids)

        key = f"{ts}/{wafer_key}/{_defect_range_key(start, end)}"
        s3_client.put_object(
            Bucket=patch_bucket, Key=key, Body=zip_data, ContentType="application/zip"
        )
        keys.append(key)

    return keys


def upload_individual_patch_images(
    s3_client: _S3Client,
    wafer_key: int,
    inspection_time: datetime,
    patch_bucket: str = DEFAULT_PATCH_BUCKET,
) -> None:
    """Upload individual template.png and defective.png to S3 (patch_images bucket).

    These are referenced by the SC import metadata as per-view contract keys
    (``s3://patch-images/.../template.png``, ``s3://patch-images/.../defective.png``)
    and must exist as standalone objects for runtime materialization.
    """
    ts = _inspection_time_str(inspection_time)
    prefix = f"{ts}/{wafer_key}"

    for name in ("template.png", "defective.png"):
        img = generate_patch_image()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        key = f"{prefix}/{name}"
        s3_client.put_object(
            Bucket=patch_bucket,
            Key=key,
            Body=buf.read(),
            ContentType="image/png",
        )


def upload_review_images(
    s3_client: _S3Client,
    wafer_key: int,
    inspection_time: datetime,
    defect_ids: list[int],
    images_per_defect: int = 5,
    review_bucket: str = DEFAULT_REVIEW_BUCKET,
) -> None:
    """Upload review images to S3 (review_images bucket)."""
    ts = _inspection_time_str(inspection_time)

    for defect_id in defect_ids:
        for img_id in range(1, images_per_defect + 1):
            img = generate_review_image()
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            buf.seek(0)

            key = f"{ts}/{wafer_key}/{defect_id:07d}_{img_id}.jpg"
            s3_client.put_object(
                Bucket=review_bucket,
                Key=key,
                Body=buf.read(),
                ContentType="image/jpeg",
            )


def review_image_filespec(
    wafer_key: int,
    inspection_time: datetime,
    defect_id: int,
    image_id: int,
    review_bucket: str = DEFAULT_REVIEW_BUCKET,
) -> str:
    """Return the S3 filespec string for a review image."""
    ts = _inspection_time_str(inspection_time)
    return f"{review_bucket}/{ts}/{wafer_key}/{defect_id:07d}_{image_id}.jpg"
