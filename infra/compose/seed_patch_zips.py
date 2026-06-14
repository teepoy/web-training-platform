"""Seed patch zip images into MinIO and populate the inspection_patch_images_zip table.

Usage: cd infra/compose && python3 seed_patch_zips.py
"""

from __future__ import annotations

import io
import os
import random
import zipfile
from datetime import datetime, timezone

import boto3
from sqlalchemy import create_engine

PATCH_SIZE = 64
DEFECTS_PER_ZIP = 500

PATCH_BUCKET = "sc-patch-images"
REVIEW_BUCKET = "sc-review-images"

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ZIPS_DB_URL = f"sqlite:///{os.path.join(DATA_DIR, 'inspection_zips.db')}"


def _generate_patch_png(side: int = PATCH_SIZE) -> bytes:
    from PIL import Image

    pixels = bytes(random.randint(0, 255) for _ in range(side * side))
    img = Image.frombytes("L", (side, side), pixels)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _time_str(dt: datetime) -> str:
    return dt.strftime("%Y%m%d_%H%M%S")


def create_patch_zips(
    wafer_key: int,
    inspection_time: datetime,
    total_defects: int,
    s3: object,
    bucket: str = PATCH_BUCKET,
) -> list[dict[str, str]]:
    ts = _time_str(inspection_time)
    refs: list[dict[str, str]] = []

    for start in range(1, total_defects + 1, DEFECTS_PER_ZIP):
        end = min(start + DEFECTS_PER_ZIP - 1, total_defects)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for did in range(start, end + 1):
                png = _generate_patch_png()
                zf.writestr(f"{did:06d}.png", png)

        key = f"{ts}/{wafer_key}/{start:06d}-{end:06d}.zip"
        s3.put_object(
            Bucket=bucket, Key=key, Body=buf.getvalue(), ContentType="application/zip"
        )
        refs.append({"bucket": bucket, "key": key})
        print(f"  uploaded zip {start:06d}-{end:06d}.zip ({start}–{end})")

    return refs


def ensure_buckets(s3: object) -> None:
    from botocore.exceptions import ClientError

    for bucket in (PATCH_BUCKET, REVIEW_BUCKET):
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
) -> None:
    from sqlalchemy import text

    ts_str = inspection_time.strftime("%Y-%m-%d %H:%M:%S.%f")
    engine = create_engine(ZIPS_DB_URL)
    with engine.connect() as conn:
        for ref in refs:
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO inspection_patch_images_zip "
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
    print(f"Inserted {len(refs)} zip references into {ZIPS_DB_URL}")


def main() -> None:
    s3_endpoint = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
    s3_access = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
    s3_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")

    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=s3_access,
        aws_secret_access_key=s3_secret,
    )

    ensure_buckets(s3)

    inspection_time = datetime(2026, 5, 26, 8, 0, 0, tzinfo=timezone.utc)
    wafer_key = 1
    total_defects = 100_000
    lot_id = "LOT-2026-001"
    wafer_id = "WAF-001"
    device = "DEVICE-DEMO-A"
    layer_id = "LAYER-M1"

    print(
        f"Generating {total_defects} defects, {DEFECTS_PER_ZIP} per zip = {total_defects // DEFECTS_PER_ZIP} zips..."
    )
    refs = create_patch_zips(wafer_key, inspection_time, total_defects, s3)
    print(f"Uploaded {len(refs)} zips to s3://{PATCH_BUCKET}/")

    insert_zips(inspection_time, lot_id, wafer_id, device, layer_id, refs)
    print("Done.")


if __name__ == "__main__":
    main()
