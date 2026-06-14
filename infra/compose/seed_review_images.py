"""Seed dummy review JPEG images into MinIO for the wafer inspection.

Usage: python3 infra/compose/seed_review_images.py
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone

import boto3
from PIL import Image

REVIEW_BUCKET = "wafer-review-images"
REVIEW_SIZE = 224


def _generate_review_png(side: int = REVIEW_SIZE) -> bytes:
    import random

    pixels = bytes(random.randint(0, 255) for _ in range(side * side))
    img = Image.frombytes("L", (side, side), pixels)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def ensure_bucket(s3: object, bucket: str) -> None:
    from botocore.exceptions import ClientError

    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)
        print(f"Created bucket: {bucket}")


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

    ensure_bucket(s3, REVIEW_BUCKET)

    inspection_time = datetime(2026, 5, 26, 8, 0, 0, tzinfo=timezone.utc)
    ts = inspection_time.strftime("%Y%m%d_%H%M%S")
    wafer_key = 1
    imaged_defects = 50
    images_per_defect = 3

    total = 0
    for defect_id in range(1, imaged_defects + 1):
        for img_id in range(1, images_per_defect + 1):
            png = _generate_review_png()
            key = f"{ts}/{wafer_key}/{defect_id:07d}_{img_id}.jpg"
            s3.put_object(
                Bucket=REVIEW_BUCKET, Key=key, Body=png, ContentType="image/png"
            )
            total += 1

    print(f"Uploaded {total} review images to s3://{REVIEW_BUCKET}/")


if __name__ == "__main__":
    main()
