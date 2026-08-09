from __future__ import annotations

from datetime import datetime
import sqlite3

import pytest
from diskcache import Cache

from infra.compose.seed_patch_zips import (
    clear_upstream_metadata_cache,
    load_inspection_seed,
)


INSPECTION_TIME = "2026-08-01 04:00:00.000000"


def _seed_inspection_db(
    path: str,
    *,
    summary_defects: int,
    defect_ids: list[int],
) -> str:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE insp_wafer_summary ("
            "wafer_key INTEGER NOT NULL, inspection_time DATETIME NOT NULL, "
            "lot_id TEXT NOT NULL, wafer_id TEXT NOT NULL, device TEXT NOT NULL, "
            "layer_id TEXT NOT NULL, defects INTEGER NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE inspect_defect ("
            "wafer_key INTEGER NOT NULL, inspection_time DATETIME NOT NULL, "
            "defect_id INTEGER NOT NULL)"
        )
        conn.execute(
            "INSERT INTO insp_wafer_summary VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                INSPECTION_TIME,
                "A123456",
                "24",
                "DEVICE-DEMO-A",
                "LAYER-M1",
                summary_defects,
            ),
        )
        conn.executemany(
            "INSERT INTO inspect_defect VALUES (?, ?, ?)",
            [(1, INSPECTION_TIME, defect_id) for defect_id in defect_ids],
        )
    return f"sqlite:///{path}"


def test_load_inspection_seed_accepts_contiguous_aligned_ids(tmp_path) -> None:
    db_url = _seed_inspection_db(
        str(tmp_path / "inspection.db"),
        summary_defects=3,
        defect_ids=[1, 2, 3],
    )

    inspection = load_inspection_seed(db_url, wafer_key=1, expected_total_defects=3)

    assert inspection.inspection_time == datetime(2026, 8, 1, 4, 0)
    assert inspection.total_defects == 3
    assert inspection.lot_id == "A123456"


def test_load_inspection_seed_selects_an_explicit_older_inspection(tmp_path) -> None:
    path = str(tmp_path / "inspection.db")
    db_url = _seed_inspection_db(path, summary_defects=3, defect_ids=[1, 2, 3])
    newer_time = "2026-08-02 04:00:00.000000"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO insp_wafer_summary VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, newer_time, "A123456", "24", "DEVICE-DEMO-A", "LAYER-M1", 3),
        )
        conn.executemany(
            "INSERT INTO inspect_defect VALUES (?, ?, ?)",
            [(1, newer_time, defect_id) for defect_id in [1, 2, 3]],
        )

    inspection = load_inspection_seed(
        db_url,
        wafer_key=1,
        expected_total_defects=3,
        inspection_time=datetime(2026, 8, 1, 4, 0),
    )

    assert inspection.inspection_time == datetime(2026, 8, 1, 4, 0)


def test_load_inspection_seed_rejects_configured_count_mismatch(tmp_path) -> None:
    db_url = _seed_inspection_db(
        str(tmp_path / "inspection.db"),
        summary_defects=3,
        defect_ids=[1, 2, 3],
    )

    with pytest.raises(ValueError, match="summary defect count"):
        load_inspection_seed(db_url, wafer_key=1, expected_total_defects=4)


def test_load_inspection_seed_rejects_non_contiguous_ids(tmp_path) -> None:
    db_url = _seed_inspection_db(
        str(tmp_path / "inspection.db"),
        summary_defects=3,
        defect_ids=[1, 2, 4],
    )

    with pytest.raises(ValueError, match="not aligned"):
        load_inspection_seed(db_url, wafer_key=1, expected_total_defects=3)


def test_clear_upstream_metadata_cache_removes_stale_queries(tmp_path) -> None:
    cache_dir = str(tmp_path / "cache")
    cache = Cache(cache_dir)
    cache.set("insps:old-range", [{"defects": 200_000}])
    cache.set("zips:old-inspection", [{"key": "old.zip"}])
    cache.close()

    assert clear_upstream_metadata_cache(cache_dir) == 2

    cache = Cache(cache_dir)
    try:
        assert len(cache) == 0
    finally:
        cache.close()
