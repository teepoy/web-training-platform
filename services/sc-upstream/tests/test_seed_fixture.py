from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sc_upstream.models import (
    Base,
    BaseZips,
    InspWaferSummaryORM,
    InspectDefectORM,
    InspectImageORM,
)
from seed_fixtures import (
    GALLERY_PROFILE_FIXTURES,
    mass_fixture_matches,
    main,
    seed_classes,
    seed_gallery_profile_inspections,
    seed_recipes,
    seed_single_summary_mass,
)


def test_seed_fixture_implementation_is_outside_runtime_package() -> None:
    service_root = Path(__file__).resolve().parents[1]

    assert (service_root / "tools" / "seed_fixtures.py").is_file()
    assert not (service_root / "src" / "sc_upstream" / "seed.py").exists()


def test_mass_fixture_matches_reusable_seed(tmp_path) -> None:
    db_path = tmp_path / "wafer.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    BaseZips.metadata.create_all(engine)
    random.seed(42)

    inspection_time = datetime.fromisoformat("2026-08-01T04:00:00")
    with Session(engine) as session:
        seed_classes(session)
        seed_recipes(session)
        seed_single_summary_mass(
            session,
            total_defects=12,
            imaged_defects=3,
            images_per_defect=2,
            commit_batch=5,
            inspection_time=inspection_time,
        )

    assert mass_fixture_matches(
        engine,
        total_defects=12,
        imaged_defects=3,
        images_per_defect=2,
        inspection_time=inspection_time,
    )
    with Session(engine) as session:
        filespecs = [row.image_filespec for row in session.query(InspectImageORM).all()]
        assert filespecs
        assert all(filespec and filespec.endswith(".png") for filespec in filespecs)
        session.query(
            InspectImageORM
        ).first().image_filespec = "s3://wafer-review-images/stale.jpg"
        session.commit()
    assert not mass_fixture_matches(
        engine,
        total_defects=12,
        imaged_defects=3,
        images_per_defect=2,
        inspection_time=inspection_time,
    )
    assert not mass_fixture_matches(
        engine,
        total_defects=13,
        imaged_defects=3,
        images_per_defect=2,
        inspection_time=inspection_time,
    )
    assert not mass_fixture_matches(
        engine,
        total_defects=12,
        imaged_defects=3,
        images_per_defect=2,
        inspection_time=datetime.fromisoformat("2026-08-02T04:00:00"),
    )


def test_gallery_profile_fixtures_coexist_with_reusable_mass_seed(tmp_path) -> None:
    db_path = tmp_path / "wafer.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    BaseZips.metadata.create_all(engine)
    random.seed(42)

    inspection_time = datetime.fromisoformat("2026-08-01T04:00:00")
    with Session(engine) as session:
        seed_classes(session)
        seed_recipes(session)
        seed_single_summary_mass(
            session,
            total_defects=12,
            imaged_defects=3,
            images_per_defect=2,
            commit_batch=5,
            inspection_time=inspection_time,
        )
        seed_gallery_profile_inspections(
            session,
            inspection_time=inspection_time,
            total_defects=6,
            imaged_defects=2,
            images_per_defect=1,
        )
        # Re-running replaces only the three fixed identities and cannot duplicate rows.
        seed_gallery_profile_inspections(
            session,
            inspection_time=inspection_time,
            total_defects=6,
            imaged_defects=2,
            images_per_defect=1,
        )

        summaries = (
            session.query(InspWaferSummaryORM)
            .order_by(InspWaferSummaryORM.wafer_key)
            .all()
        )
        assert [(row.wafer_key, row.wafer_id, row.layer_id) for row in summaries] == [
            (1, "24", "LAYER-M1"),
            *[
                (fixture.wafer_key, fixture.wafer_id, fixture.layer_id)
                for fixture in GALLERY_PROFILE_FIXTURES
            ],
        ]
        assert session.query(InspectDefectORM).count() == 12 + 3 * 6
        assert session.query(InspectImageORM).count() == 3 * 2 + 3 * 2

    assert mass_fixture_matches(
        engine,
        total_defects=12,
        imaged_defects=3,
        images_per_defect=2,
        inspection_time=inspection_time,
    )


def test_gallery_profile_cli_does_not_require_mass_only_reset_flag(tmp_path) -> None:
    db_path = tmp_path / "wafer.db"

    main(
        [
            "gallery-profiles",
            "--db-url",
            f"sqlite:///{db_path}",
            "--inspection-time",
            "2026-08-01T04:00:00",
            "--defects",
            "2",
            "--imaged",
            "1",
            "--images-per",
            "1",
        ]
    )

    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as session:
        assert session.query(InspWaferSummaryORM).count() == 3
