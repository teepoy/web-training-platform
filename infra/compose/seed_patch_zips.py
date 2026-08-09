"""Seed mock patch zip images into MinIO and inspection_patch_images_zip.

The image-parser resolver reads patch images from zip files referenced by
sc-upstream's inspection zips DB. This script creates those zip objects and
the matching SQLite metadata for local dev.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import io
import os
import struct
import zipfile
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
INSPECTION_DB_URL = f"sqlite:///{os.path.join(DATA_DIR, 'wafer_inspection.db')}"
ZIPS_DB_URL = f"sqlite:///{os.path.join(DATA_DIR, 'inspection_zips.db')}"


@dataclass(frozen=True)
class InspectionSeed:
    inspection_time: datetime
    wafer_key: int
    lot_id: str
    wafer_id: str
    device: str
    layer_id: str
    total_defects: int


def load_inspection_seed(
    inspection_db_url: str,
    wafer_key: int,
    expected_total_defects: int,
    inspection_time: datetime | None = None,
) -> InspectionSeed:
    """Load and validate the latest inspection used to build patch zip files.

    Zip lookup relies on positional 500-defect ranges, so a count-only check is
    insufficient. The source IDs must be unique and contiguous from 1 through
    the configured count before any object or metadata is written.
    """
    from sqlalchemy import text

    if expected_total_defects <= 0:
        raise ValueError("expected total defects must be greater than zero")

    engine = create_engine(inspection_db_url)
    with engine.connect() as conn:
        inspection_filter = (
            "AND inspection_time = :inspection_time "
            if inspection_time is not None
            else ""
        )
        inspection_params: dict[str, object] = {"wafer_key": wafer_key}
        if inspection_time is not None:
            inspection_params["inspection_time"] = inspection_time.strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )
        summary = (
            conn.execute(
                text(
                    "SELECT inspection_time, wafer_key, lot_id, wafer_id, device, "
                    "layer_id, defects FROM insp_wafer_summary "
                    "WHERE wafer_key = :wafer_key "
                    f"{inspection_filter}"
                    "ORDER BY inspection_time DESC LIMIT 1"
                ),
                inspection_params,
            )
            .mappings()
            .one_or_none()
        )
        if summary is None:
            scope = f"wafer_key={wafer_key}"
            if inspection_time is not None:
                scope += f", inspection_time={inspection_time.isoformat()}"
            raise ValueError(f"inspection not found for {scope}")

        inspection_time_value = summary["inspection_time"]
        stats = (
            conn.execute(
                text(
                    "SELECT COUNT(*) AS row_count, "
                    "COUNT(DISTINCT defect_id) AS distinct_count, "
                    "MIN(defect_id) AS min_id, MAX(defect_id) AS max_id "
                    "FROM inspect_defect "
                    "WHERE wafer_key = :wafer_key "
                    "AND inspection_time = :inspection_time"
                ),
                {
                    "wafer_key": wafer_key,
                    "inspection_time": inspection_time_value,
                },
            )
            .mappings()
            .one()
        )

    summary_count = int(summary["defects"])
    row_count = int(stats["row_count"])
    distinct_count = int(stats["distinct_count"])
    min_id = stats["min_id"]
    max_id = stats["max_id"]
    expected_stats = (
        expected_total_defects,
        expected_total_defects,
        1,
        expected_total_defects,
    )
    actual_stats = (row_count, distinct_count, min_id, max_id)
    if summary_count != expected_total_defects:
        raise ValueError(
            "inspection summary defect count does not match configured count: "
            f"summary={summary_count}, configured={expected_total_defects}"
        )
    if actual_stats != expected_stats:
        raise ValueError(
            "inspection defect IDs are not aligned with patch zip ranges: "
            f"rows={row_count}, distinct={distinct_count}, min={min_id}, "
            f"max={max_id}, expected=1..{expected_total_defects}"
        )

    if isinstance(inspection_time_value, datetime):
        inspection_time = inspection_time_value
    else:
        inspection_time = datetime.fromisoformat(str(inspection_time_value))

    return InspectionSeed(
        inspection_time=inspection_time,
        wafer_key=int(summary["wafer_key"]),
        lot_id=str(summary["lot_id"]),
        wafer_id=str(summary["wafer_id"]),
        device=str(summary["device"]),
        layer_id=str(summary["layer_id"]),
        total_defects=expected_total_defects,
    )


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


def clear_upstream_metadata_cache(cache_dir: str) -> int:
    """Clear cached inspection/zip queries after replacing the seed sources."""
    from diskcache import Cache

    cache = Cache(cache_dir)
    try:
        return int(cache.clear())
    finally:
        cache.close()


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
        "--inspection-db-url",
        default=os.environ.get("UPSTREAM_DB_URL", INSPECTION_DB_URL),
    )
    parser.add_argument(
        "--zips-db-url", default=os.environ.get("ZIPS_DB_URL", ZIPS_DB_URL)
    )
    parser.add_argument(
        "--upstream-cache-dir",
        default=os.environ.get(
            "SC_UPSTREAM_CACHE_DIR", os.path.join(DATA_DIR, "cache")
        ),
    )
    parser.add_argument(
        "--total-defects",
        type=int,
        default=int(os.environ.get("SC_WAFER_MOCK_DEFECTS", "300000")),
    )
    parser.add_argument("--defects-per-zip", type=int, default=DEFECTS_PER_ZIP)
    parser.add_argument("--wafer-key", type=int, default=1)
    parser.add_argument(
        "--inspection-time",
        help=(
            "Seed one existing inspection instead of the latest inspection for the wafer. "
            "Timezone offsets are treated as the mock database's local wall time."
        ),
    )
    args = parser.parse_args()

    if args.defects_per_zip <= 0:
        raise ValueError("defects per zip must be greater than zero")

    requested_inspection_time: datetime | None = None
    if args.inspection_time:
        requested_inspection_time = datetime.fromisoformat(
            args.inspection_time.replace("Z", "+00:00")
        ).replace(tzinfo=None)

    inspection = load_inspection_seed(
        args.inspection_db_url,
        args.wafer_key,
        args.total_defects,
        inspection_time=requested_inspection_time,
    )
    print(
        "Validated inspection alignment: "
        f"wafer_key={inspection.wafer_key}, "
        f"inspection_time={inspection.inspection_time.isoformat()}, "
        f"defects={inspection.total_defects}"
    )

    s3 = boto3.client(
        "s3",
        endpoint_url=args.s3_endpoint,
        aws_access_key_id=args.s3_access_key,
        aws_secret_access_key=args.s3_secret_key,
    )

    ensure_buckets(s3, (args.bucket, REVIEW_BUCKET))

    print(
        f"Generating patch zips for {inspection.total_defects} defects, "
        f"{args.defects_per_zip} per zip..."
    )
    refs = create_patch_zips(
        inspection.wafer_key,
        inspection.inspection_time,
        inspection.total_defects,
        s3,
        bucket=args.bucket,
        defects_per_zip=args.defects_per_zip,
    )
    print(f"Uploaded {len(refs)} zips to s3://{args.bucket}/")

    insert_zips(
        inspection.inspection_time,
        inspection.lot_id,
        inspection.wafer_id,
        inspection.device,
        inspection.layer_id,
        refs,
        args.zips_db_url,
    )
    cleared_entries = clear_upstream_metadata_cache(args.upstream_cache_dir)
    print(
        "Cleared SC upstream metadata cache after seed replacement: "
        f"entries={cleared_entries}, directory={args.upstream_cache_dir}"
    )
    print("Done.")


if __name__ == "__main__":
    main()
