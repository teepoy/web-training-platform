from __future__ import annotations

import argparse
import math
import os
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .models import (
    Base,
    BaseZips,
    ClassORM,
    InspRecipeORM,
    InspWaferSummaryORM,
    InspectDefectORM,
    InspectImageORM,
)

DEFAULT_UPSTREAM_DB_URL = "sqlite:///wafer_inspection.db"
DEFAULT_ZIPS_DB_URL = "sqlite:///inspection_zips.db"

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


DEFAULT_PATCH_BUCKET = "wafer-patches"
DEFAULT_REVIEW_BUCKET = "wafer-review-images"


def seed_single_summary_mass(
    session: Session,
    total_defects: int = 300_000,
    imaged_defects: int = 100,
    images_per_defect: int = 5,
    commit_batch: int = 10_000,
) -> None:
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
                    ts = inspection_time.strftime("%Y%m%d_%H%M%S")
                    filespec = f"s3://{DEFAULT_REVIEW_BUCKET}/{ts}/{wafer_key}/{defect_id:07d}_{img_id}.jpg"
                    session.add(
                        _make_image(
                            wafer_key, inspection_time, defect_id, img_id, filespec
                        )
                    )

        session.commit()
        print(f"  committed defects {start:,}–{end - 1:,}")

    print(
        f"Seed complete: 1 summary, {total_defects:,} defects, {total_images:,} images (on {imaged_defects} defects)"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Seed patch wafer inspection mock data for sc-upstream"
    )
    sub = parser.add_subparsers(dest="command", help="Seed scenario")

    mass = sub.add_parser("mass", help="1 summary + N defects + images")
    mass.add_argument(
        "--db-url",
        default=os.environ.get("UPSTREAM_DB_URL", DEFAULT_UPSTREAM_DB_URL),
        help=f"Upstream DB URL (default: {DEFAULT_UPSTREAM_DB_URL})",
    )
    mass.add_argument("--defects", type=int, default=300_000, help="Defect count")
    mass.add_argument("--imaged", type=int, default=100, help="Defects with images")
    mass.add_argument(
        "--images-per", type=int, default=5, help="Images per imaged defect"
    )
    mass.add_argument("--batch", type=int, default=10_000, help="Commit batch size")
    mass.add_argument(
        "--reset", action="store_true", help="Drop and recreate all tables"
    )

    rep = sub.add_parser("representative", help="Multi-lot/wafer representative data")
    rep.add_argument(
        "--db-url",
        default=os.environ.get("UPSTREAM_DB_URL", DEFAULT_UPSTREAM_DB_URL),
    )
    rep.add_argument("--lots", type=int, default=3)
    rep.add_argument("--wafers-per-lot", type=int, default=25)
    rep.add_argument("--inspections-per-wafer", type=int, default=4)
    rep.add_argument("--defects-min", type=int, default=10)
    rep.add_argument("--defects-max", type=int, default=200)
    rep.add_argument("--reset", action="store_true")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return

    engine = create_engine(args.db_url, echo=False)

    if args.reset:
        Base.metadata.drop_all(engine)
        BaseZips.metadata.drop_all(engine)

    Base.metadata.create_all(engine)
    BaseZips.metadata.create_all(engine)

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
            )

    print("Done.")


if __name__ == "__main__":
    main()
