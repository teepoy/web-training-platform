from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import io
import struct
from typing import Protocol
import zipfile
import zlib

from .domain import PatchArchiveDraft, ReviewImageDraft

PATCH_SIZE = 32


class ObjectStore(Protocol):
    def ensure_bucket(self, bucket: str) -> None: ...

    def put(self, *, bucket: str, key: str, body: bytes, content_type: str) -> None: ...


class BotoObjectStore:
    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> None:
        import boto3

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def ensure_bucket(self, bucket: str) -> None:
        from botocore.exceptions import ClientError

        try:
            self._client.head_bucket(Bucket=bucket)
        except ClientError:
            self._client.create_bucket(Bucket=bucket)

    def put(self, *, bucket: str, key: str, body: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )


@dataclass(frozen=True)
class PublishedArtifacts:
    review_images: tuple[ReviewImageDraft, ...]
    patch_archives: tuple[PatchArchiveDraft, ...]


class InspectionArtifactPublisher:
    def __init__(
        self,
        *,
        object_store: ObjectStore,
        patch_bucket: str,
        review_bucket: str,
    ) -> None:
        self._object_store = object_store
        self._patch_bucket = patch_bucket
        self._review_bucket = review_bucket

    def publish(
        self,
        *,
        wafer_key: int,
        inspection_time: datetime,
        total_defects: int,
        imaged_defects: int,
        images_per_defect: int,
        defects_per_archive: int,
        patch_bit_depth: int,
        reference_count: int,
        difference_count: int,
    ) -> PublishedArtifacts:
        if total_defects <= 0:
            raise ValueError("total_defects must be positive")
        if defects_per_archive <= 0:
            raise ValueError("defects_per_archive must be positive")
        if patch_bit_depth not in (8, 12, 16):
            raise ValueError("patch_bit_depth must be 8, 12, or 16")
        if reference_count <= 0 or difference_count <= 0:
            raise ValueError("reference_count and difference_count must be positive")
        if imaged_defects < 0 or images_per_defect < 0:
            raise ValueError("review image counts cannot be negative")

        self._object_store.ensure_bucket(self._patch_bucket)
        self._object_store.ensure_bucket(self._review_bucket)
        timestamp = inspection_time.strftime("%Y%m%d_%H%M%S")

        archives: list[PatchArchiveDraft] = []
        archive_id = 1
        for start in range(1, total_defects + 1, defects_per_archive):
            end = min(start + defects_per_archive - 1, total_defects)
            body = _patch_archive(
                start=start,
                end=end,
                patch_bit_depth=patch_bit_depth,
                reference_count=reference_count,
                difference_count=difference_count,
            )
            key = f"{timestamp}/{wafer_key}/{start:06d}-{end:06d}.zip"
            self._object_store.put(
                bucket=self._patch_bucket,
                key=key,
                body=body,
                content_type="application/zip",
            )
            archives.append(
                PatchArchiveDraft(
                    archive_id=archive_id,
                    s3_bucket=self._patch_bucket,
                    s3_key=key,
                )
            )
            archive_id += 1

        reviews: list[ReviewImageDraft] = []
        for defect_id in range(1, min(total_defects, imaged_defects) + 1):
            for image_id in range(1, images_per_defect + 1):
                key = f"{timestamp}/{wafer_key}/{defect_id:07d}_{image_id}.png"
                self._object_store.put(
                    bucket=self._review_bucket,
                    key=key,
                    body=_rgb_png(defect_id, image_id * 41, side=256),
                    content_type="image/png",
                )
                reviews.append(
                    ReviewImageDraft(
                        defect_id=defect_id,
                        image_id=image_id,
                        image_type="SEM_TOP",
                        image_filespec=f"s3://{self._review_bucket}/{key}",
                    )
                )
        return PublishedArtifacts(
            review_images=tuple(reviews),
            patch_archives=tuple(archives),
        )


def _patch_archive(
    *,
    start: int,
    end: int,
    patch_bit_depth: int,
    reference_count: int,
    difference_count: int,
) -> bytes:
    image_types = [
        ("PatchDefective", 128, patch_bit_depth),
        *[
            (f"PatchReference{index}", 72 + index * 32, patch_bit_depth)
            for index in range(reference_count)
        ],
        *[
            (f"PatchDifference{index}", 196 + index * 28, patch_bit_depth)
            for index in range(difference_count)
        ],
        ("PatchMask0", 1, 8),
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for defect_id in range(start, end + 1):
            for suffix, bias, bit_depth in image_types:
                archive.writestr(
                    f"{defect_id:06d}_{suffix}.png",
                    _gray_png(defect_id, bias, bit_depth),
                )
    return buffer.getvalue()


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    payload = tag + data
    return (
        struct.pack(">I", len(data))
        + payload
        + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
    )


def _rgb_png(defect_id: int, image_bias: int, *, side: int) -> bytes:
    value = (defect_id * 17 + image_bias) % 180 + 40
    accent = (defect_id * 31 + image_bias) % side
    rows = bytearray()
    for y in range(side):
        rows.append(0)
        for x in range(side):
            pixel = 230 if x == accent or y == accent else value
            rows.extend((pixel, pixel, pixel))
    return _png(side=side, bit_depth=8, color_type=2, rows=bytes(rows))


def _gray_png(defect_id: int, image_bias: int, bit_depth: int) -> bytes:
    maximum = (1 << bit_depth) - 1
    rows = bytearray()
    for y in range(PATCH_SIZE):
        rows.append(0)
        for x in range(PATCH_SIZE):
            index = y * PATCH_SIZE + x
            if index == 0:
                value = 0
            elif index == 1:
                value = maximum
            else:
                value = (defect_id * 37 + image_bias * 13 + x * 29 + y * 17) % (
                    maximum + 1
                )
            if bit_depth == 8:
                rows.append(value)
            else:
                rows.extend(struct.pack(">H", value))
    return _png(
        side=PATCH_SIZE,
        bit_depth=8 if bit_depth == 8 else 16,
        color_type=0,
        rows=bytes(rows),
    )


def _png(*, side: int, bit_depth: int, color_type: int, rows: bytes) -> bytes:
    value = b"\x89PNG\r\n\x1a\n"
    value += _png_chunk(
        b"IHDR", struct.pack(">IIBBBBB", side, side, bit_depth, color_type, 0, 0, 0)
    )
    value += _png_chunk(b"IDAT", zlib.compress(rows, 6))
    value += _png_chunk(b"IEND", b"")
    return value
