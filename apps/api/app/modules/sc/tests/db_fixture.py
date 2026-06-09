from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.modules.sc.adapter._wafer_mock.models import Base
from app.modules.sc.adapter._wafer_mock.seed import seed_classes, seed_recipes, seed_wafer_data


def create_mock_sc_db(db_path: str) -> str:
    """Create and seed a mock SC wafer inspection SQLite database.

    Uses wafer-mock ORM models and seed functions — no raw SQL.

    Args:
        db_path: Filesystem path for the new SQLite database file.

    Returns:
        The same db_path on success.
    """
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, echo=False)

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_classes(session)
        seed_recipes(session)
        base_time = datetime.now(timezone.utc).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        seed_wafer_data(
            session,
            num_lots=1,
            wafers_per_lot=3,
            inspections_per_wafer=1,
            defects_min=10,
            defects_max=10,
            base_time=base_time,
        )

    engine.dispose()
    return db_path


def teardown_mock_sc_db(db_path: str) -> None:
    """Delete the mock SC wafer inspection SQLite database file.

    Args:
        db_path: Filesystem path to the SQLite database file to delete.
    """
    if os.path.exists(db_path):
        os.remove(db_path)
