"""Test that the wafer mock seed populates the images column on inspect_defect."""

from __future__ import annotations

import tempfile

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.sc.adapter._wafer_mock.models import Base
from app.modules.sc.adapter._wafer_mock.seed import (
    seed_classes,
    seed_recipes,
    seed_single_summary_mass,
)
from app.modules.sc.tests.db_fixture import teardown_mock_sc_db


class TestSeedImages:
    """Verify images column is correctly populated by seed_single_summary_mass."""

    def test_mass_mode_images_column(self) -> None:
        """Seed 200 defects (50 imaged, 3 each) and verify images column."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            db_url = f"sqlite:///{db_path}"
            engine = create_engine(db_url, echo=False)
            Base.metadata.create_all(engine)

            with Session(engine) as session:
                seed_classes(session)
                seed_recipes(session)
                seed_single_summary_mass(
                    session,
                    total_defects=200,
                    imaged_defects=50,
                    images_per_defect=3,
                    commit_batch=200,
                )

            with Session(engine) as session:
                # Assert 50 defects have images=3
                rows = session.execute(
                    text("SELECT defect_id, images FROM inspect_defect WHERE images > 0")
                ).fetchall()
                assert len(rows) == 50, (
                    f"Expected 50 defects with images > 0, got {len(rows)}"
                )
                for row in rows:
                    assert row.images == 3, (
                        f"Defect {row.defect_id} has images={row.images}, expected 3"
                    )

                # Assert 150 defects have images=0
                count = session.execute(
                    text("SELECT COUNT(*) FROM inspect_defect WHERE images = 0")
                ).scalar()
                assert count == 150, (
                    f"Expected 150 defects with images=0, got {count}"
                )

            engine.dispose()
        finally:
            teardown_mock_sc_db(db_path)
