"""Seed mock patch zip images into MinIO and inspection_patch_images_zip.

The image-parser resolver reads patch images from zip files referenced by
sc-upstream's inspection zips DB. This script creates those zip objects and
the matching SQLite metadata for local dev.
"""

from __future__ import annotations

import argparse
import io
import os
import struct
import zipfile
from datetime import datetime, timedelta, timezone
import zlib

import boto3
from sqlalchemy import create_engine

PATCH_SIZE = 32
DEFECTS_PER_ZIP = 500

PATCH_BUCKET = "sc-patch-images"
REVIEW_BUCKET = "sc-review-images"
PATCH_IMAGE_TYPES = (
    ("PatchReference", 72),
    ("PatchDefective", 128),
    ("PatchDifference", 196),
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ZIPS_DB_URL = f"sqlite:///{os.path.join(DATA_DIR, 'inspection_zips.db')}"


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    payload = tag + data
    return (
        struct.pack(">I", len(data))
        + payload
        + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
    )


def _generate_patch_png(
    defect_id: int, image_bias: int, side: int = PATCH_SIZE
) -> bytes:
    """Generate a tiny deterministic RGB PNG without external dependencies."""
    value = (defect_id * 17 + image_bias) % 180 + 40
    accent = (defect_id * 31 + image_bias) % side
    rows = bytearray()
    for y in range(side):
        rows.append(0)
        for x in range(side):
            if x == accent or y == accent:
                rows.extend((230, 230, 230))
            else:
                rows.extend((value, value, value))
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0))
    png += _png_chunk(b"IDAT", zlib.compress(bytes(rows), 6))
    png += _png_chunk(b"IEND", b"")
    return png


def _time_str(dt: datetime) -> str:
    return dt.strftime("%Y%m%d_%H%M%S")


def create_patch_zips(
    wafer_key: int,
    inspection_time: datetime,
    total_defects: int,
    s3: object,
    bucket: str = PATCH_BUCKET,
    defects_per_zip: int = DEFECTS_PER_ZIP,
) -> list[dict[str, str]]:
    ts = _time_str(inspection_time)
    refs: list[dict[str, str]] = []

    for start in range(1, total_defects + 1, defects_per_zip):
        end = min(start + defects_per_zip - 1, total_defects)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for did in range(start, end + 1):
                for suffix, bias in PATCH_IMAGE_TYPES:
                    png = _generate_patch_png(did, bias)
                    zf.writestr(f"{did:06d}_{suffix}.png", png)

        key = f"{ts}/{wafer_key}/{start:06d}-{end:06d}.zip"
        s3.put_object(
            Bucket=bucket, Key=key, Body=buf.getvalue(), ContentType="application/zip"
        )
        refs.append({"bucket": bucket, "key": key})
        print(f"  uploaded zip {start:06d}-{end:06d}.zip ({start}–{end})")

    return refs


def ensure_buckets(s3: object, buckets: tuple[str, ...]) -> None:
    from botocore.exceptions import ClientError

    for bucket in buckets:
        try:
            s3.head_bucket(Bucket=bucket)
        except ClientError:
            s3.create_bucket(Bucket=bucket)
            print(f"Created bucket: {bucket}")


def insert_zips(
    inspection_time: datetime,
    lot_id: str,
    wafer_id: str,
    device: str,
    layer_id: str,
    refs: list[dict[str, str]],
    zips_db_url: str,
) -> None:
    from sqlalchemy import text

    ts_str = inspection_time.strftime("%Y-%m-%d %H:%M:%S.%f")
    engine = create_engine(zips_db_url)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS inspection_patch_images_zip ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "inspection_time DATETIME NOT NULL, "
                "lot_id VARCHAR(50) NOT NULL, "
                "wafer_id VARCHAR(50) NOT NULL, "
                "device VARCHAR(50) NOT NULL, "
                "layer_id VARCHAR(50) NOT NULL, "
                "s3_bucket VARCHAR(255) NOT NULL, "
                "s3_key VARCHAR(512) NOT NULL)"
            )
        )
        conn.execute(
            text(
                "DELETE FROM inspection_patch_images_zip "
                "WHERE inspection_time = :ts AND lot_id = :lot AND wafer_id = :wafer "
                "AND device = :dev AND layer_id = :layer"
            ),
            {
                "ts": ts_str,
                "lot": lot_id,
                "wafer": wafer_id,
                "dev": device,
                "layer": layer_id,
            },
        )
        for ref in refs:
            conn.execute(
                text(
                    "INSERT INTO inspection_patch_images_zip "
                    "(inspection_time, lot_id, wafer_id, device, layer_id, s3_bucket, s3_key) "
                    "VALUES (:ts, :lot, :wafer, :dev, :layer, :bucket, :key)"
                ),
                {
                    "ts": ts_str,
                    "lot": lot_id,
                    "wafer": wafer_id,
                    "dev": device,
                    "layer": layer_id,
                    "bucket": ref["bucket"],
                    "key": ref["key"],
                },
            )
        conn.commit()
    print(f"Inserted {len(refs)} zip references into {zips_db_url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed mock SC patch zip images")
    parser.add_argument(
        "--s3-endpoint", default=os.environ.get("S3_ENDPOINT", "http://localhost:9000")
    )
    parser.add_argument(
        "--s3-access-key", default=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
    )
    parser.add_argument(
        "--s3-secret-key", default=os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")
    )
    parser.add_argument(
        "--bucket", default=os.environ.get("SC_PATCH_S3_BUCKET", PATCH_BUCKET)
    )
    parser.add_argument(
        "--zips-db-url", default=os.environ.get("ZIPS_DB_URL", ZIPS_DB_URL)
    )
    parser.add_argument(
        "--total-defects",
        type=int,
        default=int(os.environ.get("SC_PATCH_ZIP_DEFECTS", "200000")),
    )
    parser.add_argument("--defects-per-zip", type=int, default=DEFECTS_PER_ZIP)
    parser.add_argument("--wafer-key", type=int, default=1)
    parser.add_argument("--inspection-time", default=None)
    parser.add_argument("--lot-id", default="A123456")
    parser.add_argument("--wafer-id", default="24")
    parser.add_argument("--device", default="DEVICE-DEMO-A")
    parser.add_argument("--layer-id", default="LAYER-M1")
    args = parser.parse_args()

    if args.inspection_time:
        inspection_time = datetime.fromisoformat(args.inspection_time)
        if inspection_time.tzinfo is None:
            inspection_time = inspection_time.replace(tzinfo=timezone.utc)
    else:
        now = datetime.now().astimezone()
        inspection_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
        if now < inspection_time:
            inspection_time -= timedelta(days=1)

    s3 = boto3.client(
        "s3",
        endpoint_url=args.s3_endpoint,
        aws_access_key_id=args.s3_access_key,
        aws_secret_access_key=args.s3_secret_key,
    )

    ensure_buckets(s3, (args.bucket, REVIEW_BUCKET))

    print(
        f"Generating patch zips for {args.total_defects} defects, "
        f"{args.defects_per_zip} per zip..."
    )
    refs = create_patch_zips(
        args.wafer_key,
        inspection_time,
        args.total_defects,
        s3,
        bucket=args.bucket,
        defects_per_zip=args.defects_per_zip,
    )
    print(f"Uploaded {len(refs)} zips to s3://{args.bucket}/")

    insert_zips(
        inspection_time,
        args.lot_id,
        args.wafer_id,
        args.device,
        args.layer_id,
        refs,
        args.zips_db_url,
    )
    print("Done.")


if __name__ == "__main__":
    main()
