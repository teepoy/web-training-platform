from __future__ import annotations
from typing import Any

import argparse
import math
import os
import random
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .images import DEFAULT_PATCH_BUCKET, DEFAULT_REVIEW_BUCKET
from .models import (
    Base,
    ClassORM,
    InspRecipeORM,
    InspWaferSummaryORM,
    InspectDefectORM,
    InspectImageORM,
)

DEFAULT_DB_URL = "sqlite:///wafer_inspection.db"

DEFECT_CLASSES: list[tuple[int, str]] = [
    (0, "No Defect"),
    (1, "Scratch"),
    (2, "Particle"),
    (3, "Pattern Defect"),
    (4, "Residue"),
    (5, "Crack"),
    (6, "Void"),
    (7, "Misalignment"),
    (8, "Thickness Variation"),
    (9, "Contamination"),
]

RECIPES: list[tuple[int, str]] = [
    (1, "RECIPE-STD-001"),
    (2, "RECIPE-STD-002"),
    (3, "RECIPE-HR-001"),
    (4, "RECIPE-EDGE-001"),
    (5, "RECIPE-FAST-001"),
]

EQUIPMENT_IDS: list[str] = [
    "EQ-TOOL-A1",
    "EQ-TOOL-A2",
    "EQ-TOOL-B1",
    "EQ-TOOL-B2",
    "EQ-TOOL-C1",
]

DEVICE_IDS: list[str] = [
    "DEVICE-LOGIC-A",
    "DEVICE-LOGIC-B",
    "DEVICE-MEMORY-A",
    "DEVICE-MEMORY-B",
    "DEVICE-SENSOR-A",
]

LAYER_IDS: list[str] = [
    "LAYER-M1",
    "LAYER-M2",
    "LAYER-M3",
    "LAYER-V1",
    "LAYER-V2",
    "LAYER-POLY",
    "LAYER-CONTACT",
    "LAYER-PASSIVATION",
]

IMAGE_TYPES: list[str] = [
    "SEM_TOP",
    "SEM_TILT",
    "OPTICAL_BRIGHT",
    "OPTICAL_DARK",
    "REVIEW_HIGH_MAG",
    "REVIEW_LOW_MAG",
]

CLASS_WEIGHTS: list[float] = [
    0.02,
    0.20,
    0.25,
    0.15,
    0.12,
    0.05,
    0.05,
    0.08,
    0.05,
    0.03,
]


def _generate_class() -> int:
    return random.choices(
        range(len(DEFECT_CLASSES[:3])), weights=CLASS_WEIGHTS[:3], k=1
    )[0]


def seed_classes(session: Session) -> None:
    existing = {c.class_number for c in session.query(ClassORM).all()}
    for class_number, name in DEFECT_CLASSES:
        if class_number not in existing:
            session.add(ClassORM(class_number=class_number, name=name))
    session.commit()


def seed_recipes(session: Session) -> None:
    existing = {r.recipe_key for r in session.query(InspRecipeORM).all()}
    for recipe_key, recipe_id in RECIPES:
        if recipe_key not in existing:
            session.add(
                InspRecipeORM(
                    recipe_key=recipe_key,
                    recipe_id=recipe_id,
                    origin_index_x=0,
                    origin_index_y=0,
                )
            )
    session.commit()


def _make_summary(
    wafer_key: int,
    inspection_time: datetime,
    lot_id: str,
    wafer_id: str,
    layer_id: str,
    recipe_key: int,
    equip_id: str,
    num_defects: int,
    num_images: int,
    origin_x: int,
    origin_y: int,
    die_size_x: int,
    die_size_y: int,
    device: str,
    center_x: int = 150_000_000,
    center_y: int = 150_000_000,
) -> InspWaferSummaryORM:
    return InspWaferSummaryORM(
        wafer_key=wafer_key,
        inspection_time=inspection_time,
        lot_id=lot_id,
        wafer_id=wafer_id,
        layer_id=layer_id,
        recipe_key=recipe_key,
        inspect_equip_id=equip_id,
        last_update=inspection_time + timedelta(minutes=random.randint(5, 60)),
        defects=num_defects,
        images=num_images,
        center_x=center_x,
        center_y=center_y,
        origin_x=origin_x,
        origin_y=origin_y,
        die_size_x=die_size_x,
        die_size_y=die_size_y,
        device=device,
    )


def _make_defect(
    wafer_key: int,
    inspection_time: datetime,
    defect_id: int,
    origin_x: int,
    origin_y: int,
    die_size_x: int,
    die_size_y: int,
    wafer_radius: int,
    images: int = 0,
    center_x: int = 150_000_000,
    center_y: int = 150_000_000,
) -> InspectDefectORM:
    class_number = _generate_class()
    angle = random.uniform(0, 2 * math.pi)
    r = random.uniform(0, wafer_radius * 0.95)
    wafer_x = center_x + int(r * math.cos(angle))
    wafer_y = center_y + int(r * math.sin(angle))
    index_x = int((wafer_x - origin_x) / die_size_x)
    index_y = int((wafer_y - origin_y) / die_size_y)
    size_x = random.randint(50, 500)
    size_y = random.randint(50, 500)
    size_d = int(math.sqrt(size_x**2 + size_y**2))
    return InspectDefectORM(
        wafer_key=wafer_key,
        inspection_time=inspection_time,
        defect_id=defect_id,
        test_id=random.randint(1, 1000),
        class_number=class_number,
        rough_bin=class_number if class_number > 0 else 1,
        wafer_x=wafer_x,
        wafer_y=wafer_y,
        index_x=index_x,
        index_y=index_y,
        adder=0,
        cluster=0,
        images=images,
        die_x=index_x,
        die_y=index_y,
        size_x=size_x,
        size_y=size_y,
        size_d=size_d,
        area=size_x * size_y,
        final_bin=random.randint(0, 255),
        manual_bin=random.randint(0, 255),
        kill_ratio=round(random.uniform(0.0, 1.0), 3),
    )


def _local_filespec(
    lot_id: str,
    wafer_id: str,
    inspection_time: datetime,
    defect_id: int,
    image_id: int,
    review_bucket: str = DEFAULT_REVIEW_BUCKET,
) -> str:
    ts = inspection_time.strftime("%Y%m%d_%H%M%S")
    return f"s3://{review_bucket}/{ts}/1/{defect_id:07d}_{image_id}.jpg"


def _make_image(
    wafer_key: int,
    inspection_time: datetime,
    defect_id: int,
    image_id: int,
    filespec: str,
) -> InspectImageORM:
    return InspectImageORM(
        wafer_key=wafer_key,
        inspection_time=inspection_time,
        defect_id=defect_id,
        image_id=image_id,
        image_type=random.choice(IMAGE_TYPES),
        image_filespec=filespec,
    )


FilespecFn = Callable[[int, datetime, int, int], str]


def _s3_review_filespec(
    wafer_key: int,
    inspection_time: datetime,
    defect_id: int,
    image_id: int,
    review_bucket: str = DEFAULT_REVIEW_BUCKET,
) -> str:
    ts = inspection_time.strftime("%Y%m%d_%H%M%S")
    return f"s3://{review_bucket}/{ts}/{wafer_key}/{defect_id:07d}_{image_id}.jpg"


def seed_single_summary_mass(
    session: Session,
    total_defects: int = 300_000,
    imaged_defects: int = 100,
    images_per_defect: int = 5,
    commit_batch: int = 10_000,
    s3_endpoint: str | None = None,
    s3_access_key: str = "minioadmin",
    s3_secret_key: str = "minioadmin",
    patch_bucket: str = DEFAULT_PATCH_BUCKET,
    review_bucket: str = DEFAULT_REVIEW_BUCKET,
) -> None:
    """Seed 1 wafer summary with many defects and images on a subset."""
    die_size_x = 8_000_000
    die_size_y = 5_000_000
    wafer_die_count_x = 37
    wafer_radius = wafer_die_count_x * die_size_x // 2
    origin_x = 145_000_000
    origin_y = 145_000_000

    wafer_key = 1
    lot_id = "LOT-2026-001"
    wafer_id = "WAF-001"
    inspection_time = datetime(2026, 5, 26, 8, 0, 0, tzinfo=timezone.utc)
    total_images = imaged_defects * images_per_defect

    if s3_endpoint:

        def _s3_fspec(wk: int, it: datetime, did: int, iid: int) -> str:
            return _s3_review_filespec(wk, it, did, iid, review_bucket=review_bucket)

        filespec_fn: FilespecFn = _s3_fspec
    else:

        def _local_fspec(wk: int, it: datetime, did: int, iid: int) -> str:
            return _local_filespec(
                lot_id, wafer_id, it, did, iid, review_bucket=review_bucket
            )

        filespec_fn: FilespecFn = _local_fspec

    summary = _make_summary(
        wafer_key=wafer_key,
        inspection_time=inspection_time,
        lot_id=lot_id,
        wafer_id=wafer_id,
        layer_id="LAYER-M1",
        recipe_key=1,
        equip_id="EQ-TOOL-A1",
        num_defects=total_defects,
        num_images=total_images,
        origin_x=origin_x,
        origin_y=origin_y,
        die_size_x=die_size_x,
        die_size_y=die_size_y,
        device="DEVICE-DEMO-A",
    )
    session.add(summary)
    session.flush()

    print(f"Seeding {total_defects:,} defects (batch size {commit_batch:,})...")
    for start in range(1, total_defects + 1, commit_batch):
        end = min(start + commit_batch, total_defects + 1)
        for defect_id in range(start, end):
            images = images_per_defect if defect_id <= imaged_defects else 0
            session.add(
                _make_defect(
                    wafer_key,
                    inspection_time,
                    defect_id,
                    origin_x,
                    origin_y,
                    die_size_x,
                    die_size_y,
                    wafer_radius,
                    images=images,
                )
            )

            if defect_id <= imaged_defects:
                for img_id in range(1, images_per_defect + 1):
                    session.add(
                        _make_image(
                            wafer_key,
                            inspection_time,
                            defect_id,
                            img_id,
                            filespec_fn(wafer_key, inspection_time, defect_id, img_id),
                        )
                    )

        session.commit()
        print(f"  committed defects {start:,}–{end - 1:,}")

    print(
        f"Seed complete: 1 summary, {total_defects:,} defects, {total_images:,} images (on {imaged_defects} defects)"
    )

    if s3_endpoint:
        _upload_s3_images(
            wafer_key,
            inspection_time,
            total_defects,
            imaged_defects,
            images_per_defect,
            s3_endpoint,
            s3_access_key,
            s3_secret_key,
            patch_bucket=patch_bucket,
            review_bucket=review_bucket,
        )


def seed_wafer_data(
    session: Session,
    num_lots: int = 3,
    wafers_per_lot: int = 25,
    inspections_per_wafer: int = 4,
    defects_min: int = 10,
    defects_max: int = 200,
    images_per_defect_min: int = 1,
    images_per_defect_max: int = 4,
    base_time: datetime | None = None,
    s3_endpoint: str | None = None,
    s3_access_key: str = "minioadmin",
    s3_secret_key: str = "minioadmin",
    patch_bucket: str = DEFAULT_PATCH_BUCKET,
    review_bucket: str = DEFAULT_REVIEW_BUCKET,
) -> None:
    """Seed representative wafer inspection data spanning multiple lots/wafers."""
    if base_time is None:
        base_time = datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)

    die_size_x = 8_000_000
    die_size_y = 5_000_000
    wafer_die_count_x = 37
    wafer_radius = wafer_die_count_x * die_size_x // 2
    origin_x = 145_000_000
    origin_y = 145_000_000
    recipe_keys = [r[0] for r in RECIPES]

    s3_records: list[tuple[int, datetime, int, int, int]] = []

    for lot_idx in range(1, num_lots + 1):
        lot_id = f"LOT-2026-{lot_idx:03d}"
        inspection_offset = timedelta(days=(lot_idx - 1) * 7)

        for wafer_idx in range(1, wafers_per_lot + 1):
            wafer_key = (lot_idx - 1) * 1000 + wafer_idx

            for insp_idx in range(inspections_per_wafer):
                inspection_time = (
                    base_time
                    + inspection_offset
                    + timedelta(hours=insp_idx * 6 + random.randint(0, 120))
                )
                num_defects = random.randint(defects_min, defects_max)
                num_images = 0

                summary = _make_summary(
                    wafer_key=wafer_key,
                    inspection_time=inspection_time,
                    lot_id=lot_id,
                    wafer_id=f"WAF-{wafer_idx:03d}",
                    layer_id=random.choice(LAYER_IDS),
                    recipe_key=random.choice(recipe_keys),
                    equip_id=random.choice(EQUIPMENT_IDS),
                    num_defects=num_defects,
                    num_images=0,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    die_size_x=die_size_x,
                    die_size_y=die_size_y,
                    device=random.choice(DEVICE_IDS),
                )
                session.add(summary)

                max_img_per_defect = 0
                for defect_id in range(1, num_defects + 1):
                    n_imgs = random.randint(
                        images_per_defect_min, images_per_defect_max
                    )
                    session.add(
                        _make_defect(
                            wafer_key,
                            inspection_time,
                            defect_id,
                            origin_x,
                            origin_y,
                            die_size_x,
                            die_size_y,
                            wafer_radius,
                            images=n_imgs,
                        )
                    )
                    if n_imgs > max_img_per_defect:
                        max_img_per_defect = n_imgs
                    for img_id in range(1, n_imgs + 1):
                        if s3_endpoint:
                            filespec = _s3_review_filespec(
                                wafer_key,
                                inspection_time,
                                defect_id,
                                img_id,
                                review_bucket=review_bucket,
                            )
                        else:
                            filespec = _local_filespec(
                                lot_id,
                                f"WAF-{wafer_idx:03d}",
                                inspection_time,
                                defect_id,
                                img_id,
                                review_bucket=review_bucket,
                            )
                        session.add(
                            _make_image(
                                wafer_key, inspection_time, defect_id, img_id, filespec
                            )
                        )
                        num_images += 1

                summary.images = num_images

                if s3_endpoint and num_defects > 0:
                    s3_records.append(
                        (
                            wafer_key,
                            inspection_time,
                            num_defects,
                            num_defects,
                            max_img_per_defect,
                        )
                    )

            if wafer_idx % 5 == 0:
                session.commit()

        session.commit()

    print(f"Seeded {num_lots} lots, {num_lots * wafers_per_lot} wafers")

    if s3_endpoint and s3_records:
        for (
            wafer_key,
            inspection_time,
            total_defects,
            imaged_defects,
            imgs_per,
        ) in s3_records:
            _upload_s3_images(
                wafer_key,
                inspection_time,
                total_defects,
                imaged_defects,
                imgs_per,
                s3_endpoint,
                s3_access_key,
                s3_secret_key,
                patch_bucket=patch_bucket,
                review_bucket=review_bucket,
            )


def _upload_s3_images(
    wafer_key: int,
    inspection_time: datetime,
    total_defects: int,
    imaged_defects: int,
    images_per_defect: int,
    s3_endpoint: str,
    s3_access_key: str,
    s3_secret_key: str,
    patch_bucket: str = DEFAULT_PATCH_BUCKET,
    review_bucket: str = DEFAULT_REVIEW_BUCKET,
) -> None:
    import boto3  # pyright: ignore[reportMissingImports]

    from .images import (
        upload_individual_patch_images,
        upload_patch_zips,
        upload_review_images,
    )

    s3: Any = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=s3_access_key,
        aws_secret_access_key=s3_secret_key,
    )

    print(
        f"Uploading patch images to S3 ({total_defects:,} defects in batches of 500)..."
    )
    patch_keys = upload_patch_zips(
        s3, wafer_key, inspection_time, total_defects, patch_bucket=patch_bucket
    )
    print(f"  uploaded {len(patch_keys)} patch zips")

    print("Uploading individual patch images (template.png, defective.png)...")
    upload_individual_patch_images(
        s3, wafer_key, inspection_time, patch_bucket=patch_bucket
    )
    print("  uploaded individual patch images")

    if imaged_defects > 0:
        defect_ids = list(range(1, imaged_defects + 1))
        print(
            f"Uploading review images to S3 ({len(defect_ids)} defects x {images_per_defect} images)..."
        )
        upload_review_images(
            s3,
            wafer_key,
            inspection_time,
            defect_ids,
            images_per_defect,
            review_bucket=review_bucket,
        )
        print(f"  uploaded {len(defect_ids) * images_per_defect} review images")

    print("S3 upload complete.")


def _build_s3_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--s3-endpoint",
        default=os.environ.get("S3_ENDPOINT"),
        help="S3 endpoint URL for image uploads (e.g. http://localhost:9000)",
    )
    parser.add_argument(
        "--s3-access-key",
        default=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
        help="S3 access key (default: minioadmin)",
    )
    parser.add_argument(
        "--s3-secret-key",
        default=os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        help="S3 secret key (default: minioadmin)",
    )
    parser.add_argument(
        "--patch-bucket",
        default=os.environ.get("WAFER_PATCH_BUCKET", DEFAULT_PATCH_BUCKET),
        help=f"Patch images S3 bucket (default: {DEFAULT_PATCH_BUCKET})",
    )
    parser.add_argument(
        "--review-bucket",
        default=os.environ.get("WAFER_REVIEW_BUCKET", DEFAULT_REVIEW_BUCKET),
        help=f"Review images S3 bucket (default: {DEFAULT_REVIEW_BUCKET})",
    )


def _ensure_s3_buckets(
    s3_endpoint: str,
    access_key: str,
    secret_key: str,
    patch_bucket: str = DEFAULT_PATCH_BUCKET,
    review_bucket: str = DEFAULT_REVIEW_BUCKET,
) -> None:
    import boto3  # pyright: ignore[reportMissingImports]
    from botocore.exceptions import ClientError  # pyright: ignore[reportMissingImports]

    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    for bucket in (patch_bucket, review_bucket):
        try:
            s3.head_bucket(Bucket=bucket)
        except ClientError:
            s3.create_bucket(Bucket=bucket)
            print(f"Created S3 bucket: {bucket}")


def main(argv: list[str] | None = None) -> None:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--db-url", default=os.environ.get("WAFER_DB_URL", DEFAULT_DB_URL)
    )
    shared.add_argument(
        "--reset", action="store_true", help="Drop and recreate all tables"
    )

    parser = argparse.ArgumentParser(
        description="Seed semiconductor wafer inspection mock data"
    )
    sub = parser.add_subparsers(dest="command", help="Seed scenario")

    mass = sub.add_parser(
        "mass",
        parents=[shared],
        help="1 summary + N defects + images on first M defects",
    )
    mass.add_argument(
        "--defects",
        type=int,
        default=300_000,
        help="Total defect count (default: 300_000)",
    )
    mass.add_argument(
        "--imaged", type=int, default=100, help="Defects with images (default: 100)"
    )
    mass.add_argument(
        "--images-per",
        type=int,
        default=5,
        help="Images per imaged defect (default: 5)",
    )
    mass.add_argument(
        "--batch", type=int, default=10_000, help="Commit batch size (default: 10_000)"
    )
    _build_s3_args(mass)

    rep = sub.add_parser(
        "representative", parents=[shared], help="Multi-lot/wafer representative data"
    )
    rep.add_argument("--lots", type=int, default=3)
    rep.add_argument("--wafers-per-lot", type=int, default=25)
    rep.add_argument("--inspections-per-wafer", type=int, default=4)
    rep.add_argument("--defects-min", type=int, default=10)
    rep.add_argument("--defects-max", type=int, default=200)
    _build_s3_args(rep)

    args = parser.parse_args(argv)

    s3_endpoint: str | None = getattr(args, "s3_endpoint", None) or None
    s3_access_key: str = getattr(args, "s3_access_key", "minioadmin")
    s3_secret_key: str = getattr(args, "s3_secret_key", "minioadmin")
    patch_bucket: str = getattr(args, "patch_bucket", DEFAULT_PATCH_BUCKET)
    review_bucket: str = getattr(args, "review_bucket", DEFAULT_REVIEW_BUCKET)

    if s3_endpoint:
        try:
            import boto3  # noqa: F401  # pyright: ignore[reportMissingImports]
        except ImportError:
            print(
                "Error: boto3 is required for S3 image uploads. Install with: pip install wafer-mock[s3]",
                file=__import__("sys").stderr,
            )
            raise SystemExit(1)
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            print(
                "Error: Pillow is required for image generation. Install with: pip install wafer-mock[s3]",
                file=__import__("sys").stderr,
            )
            raise SystemExit(1)
        _ensure_s3_buckets(
            s3_endpoint,
            s3_access_key,
            s3_secret_key,
            patch_bucket=patch_bucket,
            review_bucket=review_bucket,
        )

    engine = create_engine(args.db_url, echo=False)

    if args.reset:
        Base.metadata.drop_all(engine)

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_classes(session)
        seed_recipes(session)

        if args.command == "mass":
            seed_single_summary_mass(
                session,
                total_defects=args.defects,
                imaged_defects=args.imaged,
                images_per_defect=args.images_per,
                commit_batch=args.batch,
                s3_endpoint=s3_endpoint,
                s3_access_key=s3_access_key,
                s3_secret_key=s3_secret_key,
                patch_bucket=patch_bucket,
                review_bucket=review_bucket,
            )
        else:
            seed_wafer_data(
                session,
                num_lots=args.lots,
                wafers_per_lot=args.wafers_per_lot,
                inspections_per_wafer=args.inspections_per_wafer,
                defects_min=args.defects_min,
                defects_max=args.defects_max,
                s3_endpoint=s3_endpoint,
                s3_access_key=s3_access_key,
                s3_secret_key=s3_secret_key,
                patch_bucket=patch_bucket,
                review_bucket=review_bucket,
            )

    print("Done.")


if __name__ == "__main__":
    main()
