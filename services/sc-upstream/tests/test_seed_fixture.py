from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sc_upstream.models import Base, BaseZips
from sc_upstream.seed import (
    mass_fixture_matches,
    seed_classes,
    seed_recipes,
    seed_single_summary_mass,
)


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
