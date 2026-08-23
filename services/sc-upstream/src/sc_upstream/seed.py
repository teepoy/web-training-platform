from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
import os
import random
from datetime import datetime, timedelta

from sqlalchemy import create_engine, func, inspect, or_
from sqlalchemy.engine import Engine
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


DIE_RANGE: int = 3
DIE_CORNER_FRACTION: float = 0.3


def _make_defect(
    wafer_key: int,
    inspection_time: datetime,
    defect_id: int,
    origin_x: int,
    origin_y: int,
    die_size_x: int,
    die_size_y: int,
    images: int = 0,
    center_x: int = 150_000_000,
    center_y: int = 150_000_000,
) -> InspectDefectORM:
    class_number = _generate_class()
    die_idx_x = random.randint(-DIE_RANGE, DIE_RANGE)
    die_idx_y = random.randint(-DIE_RANGE, DIE_RANGE)
    max_offset_x = int(die_size_x * DIE_CORNER_FRACTION)
    max_offset_y = int(die_size_y * DIE_CORNER_FRACTION)
    offset_x = random.randint(0, max_offset_x)
    offset_y = random.randint(0, max_offset_y)
    wafer_x = center_x + die_idx_x * die_size_x + offset_x
    wafer_y = center_y + die_idx_y * die_size_y + offset_y
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


@dataclass(frozen=True)
class GalleryProfileFixture:
    wafer_key: int
    wafer_id: str
    layer_id: str


GALLERY_PROFILE_FIXTURES: tuple[GalleryProfileFixture, ...] = (
    GalleryProfileFixture(wafer_key=81, wafer_id="GRAY8-1R1D", layer_id="LAYER-GRAY8"),
    GalleryProfileFixture(
        wafer_key=82,
        wafer_id="GRAY16-1R1D",
        layer_id="LAYER-GRAY16-1X",
    ),
    GalleryProfileFixture(
        wafer_key=83,
        wafer_id="GRAY16-2R2D",
        layer_id="LAYER-GRAY16-2X",
    ),
)


def seed_single_summary_mass(
    session: Session,
    total_defects: int = 300_000,
    imaged_defects: int = 100,
    images_per_defect: int = 5,
    commit_batch: int = 10_000,
    inspection_time: datetime | None = None,
    *,
    wafer_key: int = 1,
    lot_id: str = "A123456",
    wafer_id: str = "24",
    layer_id: str = "LAYER-M1",
    equip_id: str = "EQ-TOOL-A1",
    device: str = "DEVICE-DEMO-A",
) -> None:
    die_size_x = 8_000_000
    die_size_y = 5_000_000
    origin_x = 145_000_000
    origin_y = 145_000_000

    if inspection_time is None:
        now = datetime.now().astimezone()
        inspection_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
        if now < inspection_time:
            inspection_time -= timedelta(days=1)
    imaged_count = min(total_defects, imaged_defects)
    total_images = imaged_count * images_per_defect

    summary = _make_summary(
        wafer_key=wafer_key,
        inspection_time=inspection_time,
        lot_id=lot_id,
        wafer_id=wafer_id,
        layer_id=layer_id,
        recipe_key=1,
        equip_id=equip_id,
        num_defects=total_defects,
        num_images=total_images,
        origin_x=origin_x,
        origin_y=origin_y,
        die_size_x=die_size_x,
        die_size_y=die_size_y,
        device=device,
    )
    session.add(summary)
    session.flush()

    print(
        f"Seeding wafer_key={wafer_key} with {total_defects:,} defects "
        f"(batch size {commit_batch:,})..."
    )
    for start in range(1, total_defects + 1, commit_batch):
        end = min(start + commit_batch, total_defects + 1)
        for defect_id in range(start, end):
            images = images_per_defect if defect_id <= imaged_count else 0
            session.add(
                _make_defect(
                    wafer_key,
                    inspection_time,
                    defect_id,
                    origin_x,
                    origin_y,
                    die_size_x,
                    die_size_y,
                    images=images,
                )
            )

            if defect_id <= imaged_count:
                for img_id in range(1, images_per_defect + 1):
                    ts = inspection_time.strftime("%Y%m%d_%H%M%S")
                    filespec = f"s3://{DEFAULT_REVIEW_BUCKET}/{ts}/{wafer_key}/{defect_id:07d}_{img_id}.png"
                    session.add(
                        _make_image(
                            wafer_key, inspection_time, defect_id, img_id, filespec
                        )
                    )

        session.commit()
        print(f"  committed defects {start:,}–{end - 1:,}")

    print(
        f"Seed complete: wafer_key={wafer_key}, 1 summary, {total_defects:,} defects, "
        f"{total_images:,} images (on {imaged_count} defects)"
    )


def seed_gallery_profile_inspections(
    session: Session,
    *,
    inspection_time: datetime,
    total_defects: int = 64,
    imaged_defects: int = 8,
    images_per_defect: int = 1,
) -> None:
    """Replace the three small gallery profile fixtures without touching other wafers."""
    if total_defects <= 0:
        raise ValueError("gallery profile defect count must be greater than zero")
    if imaged_defects < 0 or images_per_defect < 0:
        raise ValueError("gallery profile image counts cannot be negative")

    for fixture in GALLERY_PROFILE_FIXTURES:
        identity_filters = (
            InspectImageORM.wafer_key == fixture.wafer_key,
            InspectImageORM.inspection_time == inspection_time,
        )
        session.query(InspectImageORM).filter(*identity_filters).delete(
            synchronize_session=False
        )
        session.query(InspectDefectORM).filter(
            InspectDefectORM.wafer_key == fixture.wafer_key,
            InspectDefectORM.inspection_time == inspection_time,
        ).delete(synchronize_session=False)
        session.query(InspWaferSummaryORM).filter(
            InspWaferSummaryORM.wafer_key == fixture.wafer_key,
            InspWaferSummaryORM.inspection_time == inspection_time,
        ).delete(synchronize_session=False)
        session.commit()

        seed_single_summary_mass(
            session,
            total_defects=total_defects,
            imaged_defects=imaged_defects,
            images_per_defect=images_per_defect,
            commit_batch=total_defects,
            inspection_time=inspection_time,
            wafer_key=fixture.wafer_key,
            lot_id="GALLERY-VQA",
            wafer_id=fixture.wafer_id,
            layer_id=fixture.layer_id,
            equip_id="EQ-TOOL-A1",
            device="DEVICE-GALLERY-VQA",
        )


def mass_fixture_matches(
    engine: Engine,
    *,
    total_defects: int,
    imaged_defects: int,
    images_per_defect: int,
    inspection_time: datetime | None = None,
) -> bool:
    """Return whether the existing database is the requested mass fixture."""

    table_names = {
        InspWaferSummaryORM.__tablename__,
        InspectDefectORM.__tablename__,
        InspectImageORM.__tablename__,
    }
    inspector = inspect(engine)
    if any(not inspector.has_table(table_name) for table_name in table_names):
        return False

    with Session(engine) as session:
        summary_query = session.query(InspWaferSummaryORM).filter(
            InspWaferSummaryORM.wafer_key == 1
        )
        if inspection_time is not None:
            summary_query = summary_query.filter(
                InspWaferSummaryORM.inspection_time == inspection_time
            )
        summaries = summary_query.all()
        if len(summaries) != 1:
            return False
        summary = summaries[0]
        identity_filters = (
            InspectDefectORM.wafer_key == summary.wafer_key,
            InspectDefectORM.inspection_time == summary.inspection_time,
        )
        defect_stats = (
            session.query(
                func.count(InspectDefectORM.defect_id),
                func.count(func.distinct(InspectDefectORM.defect_id)),
                func.min(InspectDefectORM.defect_id),
                func.max(InspectDefectORM.defect_id),
            )
            .filter(*identity_filters)
            .one()
        )
        image_identity_filters = (
            InspectImageORM.wafer_key == summary.wafer_key,
            InspectImageORM.inspection_time == summary.inspection_time,
        )
        image_count = int(
            session.query(func.count(InspectImageORM.image_id))
            .filter(*image_identity_filters)
            .scalar()
        )
        invalid_image_locator_count = int(
            session.query(func.count(InspectImageORM.image_id))
            .filter(
                *image_identity_filters,
                or_(
                    InspectImageORM.image_filespec.is_(None),
                    ~InspectImageORM.image_filespec.like(
                        f"s3://{DEFAULT_REVIEW_BUCKET}/%.png"
                    ),
                ),
            )
            .scalar()
        )

    expected_images = min(total_defects, imaged_defects) * images_per_defect
    return (
        int(summary.defects) == total_defects
        and int(summary.images) == expected_images
        and (
            inspection_time is None
            or summary.inspection_time.replace(tzinfo=None)
            == inspection_time.replace(tzinfo=None)
        )
        and tuple(int(value or 0) for value in defect_stats)
        == (total_defects, total_defects, 1, total_defects)
        and image_count == expected_images
        and invalid_image_locator_count == 0
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

    gallery = sub.add_parser(
        "gallery-profiles",
        help="Three small inspections covering 8/16-bit gallery profile shapes",
    )
    gallery.add_argument(
        "--db-url",
        default=os.environ.get("UPSTREAM_DB_URL", DEFAULT_UPSTREAM_DB_URL),
        help=f"Upstream DB URL (default: {DEFAULT_UPSTREAM_DB_URL})",
    )
    gallery.add_argument("--defects", type=int, default=64)
    gallery.add_argument("--imaged", type=int, default=8)
    gallery.add_argument("--images-per", type=int, default=1)
    gallery.add_argument(
        "--inspection-time",
        type=datetime.fromisoformat,
        required=True,
        help="Fixed ISO inspection time shared by wafer keys 81, 82, and 83",
    )
    mass.add_argument("--defects", type=int, default=300_000, help="Defect count")
    mass.add_argument("--imaged", type=int, default=100, help="Defects with images")
    mass.add_argument(
        "--images-per", type=int, default=5, help="Images per imaged defect"
    )
    mass.add_argument("--batch", type=int, default=10_000, help="Commit batch size")
    mass.add_argument(
        "--inspection-time",
        type=datetime.fromisoformat,
        default=None,
        help="Fixed ISO inspection time for a repeatable fixture",
    )
    mass.add_argument(
        "--reset", action="store_true", help="Drop and recreate all tables"
    )
    mass.add_argument(
        "--reuse-matching",
        action="store_true",
        help=("Reuse an existing mass fixture when counts match; otherwise replace it"),
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

    if args.command == "mass" and args.reset and args.reuse_matching:
        parser.error("--reset and --reuse-matching are mutually exclusive")

    if args.command == "mass" and args.reuse_matching:
        if mass_fixture_matches(
            engine,
            total_defects=args.defects,
            imaged_defects=args.imaged,
            images_per_defect=args.images_per,
            inspection_time=args.inspection_time,
        ):
            print(
                "Reusing matching mass fixture: "
                f"defects={args.defects:,}, "
                f"images={min(args.defects, args.imaged) * args.images_per:,}"
            )
            print("Done.")
            return
        print("Existing mass fixture is missing or differs; replacing it.")

    if getattr(args, "reset", False) or (
        args.command == "mass" and args.reuse_matching
    ):
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
                inspection_time=args.inspection_time,
            )
        elif args.command == "gallery-profiles":
            seed_gallery_profile_inspections(
                session,
                inspection_time=args.inspection_time,
                total_defects=args.defects,
                imaged_defects=args.imaged,
                images_per_defect=args.images_per,
            )

    print("Done.")


if __name__ == "__main__":
    main()
