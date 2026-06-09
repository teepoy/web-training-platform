from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import cast

import polars as pl
import pytest
from app.modules.sc.adapter._wafer_mock.sqlite_upstream import SqliteScUpstream
from app.modules.sc.app.services.import_rows import (
    _geometry_from_inspection,
    iter_patch_samples_from_upstream_chunk,
)
from app.modules.sc.domain.models import ScInspectionRecord
from app.modules.sc.tests.db_fixture import create_mock_sc_db, teardown_mock_sc_db


@pytest.mark.asyncio
async def test_read_seeded_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    create_mock_sc_db(db_path)
    try:
        upstream = SqliteScUpstream(db_url=f"sqlite:///{db_path}")
        lf = await upstream._read("SELECT * FROM insp_wafer_summary")
        df = lf.collect()
        assert len(df) > 0, "Should have seeded inspection rows"
        assert "wafer_key" in df.columns
        assert "inspection_time" in df.columns
    finally:
        teardown_mock_sc_db(db_path)


@pytest.mark.asyncio
async def test_read_empty_table(tmp_path):
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE test (id INTEGER)")
    conn.close()
    upstream = SqliteScUpstream(db_url=f"sqlite:///{db_path}")
    lf = await upstream._read("SELECT * FROM test")
    df = lf.collect()
    assert len(df) == 0


@pytest.mark.asyncio
async def test_list_samples_computes_coords(tmp_path):
    """Verify list_samples returns die_x/y, reticle_x/y computed columns."""
    db_path = str(tmp_path / "test.db")
    create_mock_sc_db(db_path)
    try:
        upstream = SqliteScUpstream(db_url=f"sqlite:///{db_path}")

        lf = await upstream._read("SELECT * FROM insp_wafer_summary LIMIT 1")
        insp = lf.collect()
        # SQLAlchemy DateTime on SQLite stores as string without timezone
        insp_time_str: str = insp["inspection_time"][0]
        insp_time = datetime.strptime(insp_time_str, "%Y-%m-%d %H:%M:%S.%f")
        wafer_key: int = int(insp["wafer_key"][0])

        df = await upstream.list_samples(
            inspection_time=insp_time,
            wafer_key=wafer_key,
            offset=0,
            count=5,
            reticle_size_x=1,
            reticle_size_y=1,
        )
        df = df.collect()

        assert len(df) > 0
        for col in [
            "defect_id",
            "wafer_x",
            "wafer_y",
            "die_x",
            "die_y",
            "reticle_x",
            "reticle_y",
            "class_number",
            "rough_bin",
            "images",
        ]:
            assert col in df.columns, f"Missing column: {col}"

        origin_x: int = int(insp["origin_x"][0])
        dx: int = int(insp["die_size_x"][0])
        row = df.row(0, named=True)
        expected_die_x = (row["wafer_x"] - origin_x) % dx
        assert row["die_x"] == expected_die_x
    finally:
        teardown_mock_sc_db(db_path)


@pytest.mark.asyncio
async def test_list_samples_scales_reticle_die_offsets_by_die_size(tmp_path):
    db_path = str(tmp_path / "reticle.db")
    create_mock_sc_db(db_path)
    try:
        upstream = SqliteScUpstream(db_url=f"sqlite:///{db_path}")
        insp = (
            await upstream._read("SELECT * FROM insp_wafer_summary LIMIT 1")
        ).collect()
        insp_time = datetime.fromisoformat(str(insp["inspection_time"][0]))
        wafer_key = int(insp["wafer_key"][0])
        die_size_x = int(insp["die_size_x"][0])
        die_size_y = int(insp["die_size_y"][0])

        df = (
            await upstream.list_samples(
                inspection_time=insp_time,
                wafer_key=wafer_key,
                offset=0,
                count=10,
                reticle_size_x=3,
                reticle_size_y=5,
            )
        ).collect()

        assert len(df) > 0
        assert cast(int, df["reticle_x"].max()) < 3 * die_size_x
        assert cast(int, df["reticle_y"].max()) < 5 * die_size_y
        for row in df.iter_rows(named=True):
            assert (row["reticle_x"] - row["die_x"]) % die_size_x == 0
            assert (row["reticle_y"] - row["die_y"]) % die_size_y == 0
    finally:
        teardown_mock_sc_db(db_path)


@pytest.mark.asyncio
async def test_list_wafer_points_with_sampling(tmp_path):
    """Verify wafer_points returns computed coords and respects sampling."""
    db_path = str(tmp_path / "test.db")
    create_mock_sc_db(db_path)
    try:
        upstream = SqliteScUpstream(db_url=f"sqlite:///{db_path}")
        lf = await upstream._read("SELECT * FROM insp_wafer_summary LIMIT 1")
        insp = lf.collect()
        insp_time = insp["inspection_time"][0]
        wafer_key = int(insp["wafer_key"][0])

        if isinstance(insp_time, str):
            insp_time = datetime.fromisoformat(insp_time)

        df = await upstream.list_wafer_points(
            insp_time,
            wafer_key,
            reticle_size_x=1,
            reticle_size_y=1,
        )
        df = df.collect()

        for col in [
            "defect_id",
            "wafer_x",
            "wafer_y",
            "die_x",
            "die_y",
            "reticle_x",
            "reticle_y",
            "class_number",
            "rough_bin",
            "images",
        ]:
            assert col in df.columns, f"Missing: {col}"

        imaged = df.filter(pl.col("images") > 0)
        assert len(imaged) > 0, "Should retain all imaged defects"
    finally:
        teardown_mock_sc_db(db_path)


@pytest.mark.asyncio
async def test_list_inspections(tmp_path):
    """Verify list_inspections returns LazyFrame with joined recipe columns."""
    db_path = str(tmp_path / "test.db")
    create_mock_sc_db(db_path)
    try:
        upstream = SqliteScUpstream(db_url=f"sqlite:///{db_path}")
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        end = datetime(2030, 1, 1, tzinfo=timezone.utc)
        lf = await upstream.list_inspections(start, end)
        df = lf.collect()
        assert "wafer_key" in df.columns
        assert "inspection_time" in df.columns
        assert "lot_id" in df.columns
        assert "recipe_id" in df.columns  # from insp_recipe JOIN
        assert "origin_index_x" in df.columns  # from insp_recipe JOIN
        assert "wafer_id" in df.columns
        assert len(df) > 0
    finally:
        teardown_mock_sc_db(db_path)


@pytest.mark.asyncio
async def test_stream_batches(tmp_path):
    """Verify stream yields data in batches of pl.DataFrame."""
    db_path = str(tmp_path / "test.db")
    create_mock_sc_db(db_path)
    try:
        upstream = SqliteScUpstream(db_url=f"sqlite:///{db_path}")

        # Get an inspection from the seeded DB
        lf = await upstream._read("SELECT * FROM insp_wafer_summary LIMIT 1")
        insp = lf.collect()
        insp_time_str: str = insp["inspection_time"][0]
        # Convert to ISO format (realistic caller input per Protocol contract)
        insp_dt = datetime.strptime(insp_time_str, "%Y-%m-%d %H:%M:%S.%f")
        iso_time = insp_dt.isoformat()
        wafer_key: int = int(insp["wafer_key"][0])

        batches: list[pl.DataFrame] = []
        async for batch in upstream.stream(iso_time, wafer_key):
            assert isinstance(batch, pl.DataFrame), "Each batch must be a pl.DataFrame"
            for col in [
                "defect_id",
                "inspection_time",
                "wafer_key",
                "lot_id",
                "wafer_x",
                "wafer_y",
                "die_x",
                "die_y",
                "rough_bin",
            ]:
                assert col in batch.columns, f"Missing stream column: {col}"
            normalized = list(iter_patch_samples_from_upstream_chunk(batch))
            assert normalized, "Stream batch must normalize into PatchSample rows"
            assert normalized[0].lot_id
            assert normalized[0].defect_id
            batches.append(batch)

        total = sum(len(b) for b in batches)
        # Seeded data has 10 defects per wafer, all in one (or few) batches
        assert total > 0, "Should have at least some rows"
        # Each batch should not exceed BATCH_SIZE (50K)
        for i, b in enumerate(batches):
            assert len(b) <= 50_000, f"Batch {i} exceeds 50K rows"
    finally:
        teardown_mock_sc_db(db_path)


@pytest.mark.asyncio
async def test_stream_offset_skips_rows(tmp_path):
    """stream(offset=N) skips the first N rows in deterministic defect_id order."""
    db_path = str(tmp_path / "test.db")
    create_mock_sc_db(db_path)
    try:
        upstream = SqliteScUpstream(db_url=f"sqlite:///{db_path}")
        lf = await upstream._read("SELECT * FROM insp_wafer_summary LIMIT 1")
        insp = lf.collect()
        insp_time_str: str = insp["inspection_time"][0]
        insp_dt = datetime.strptime(insp_time_str, "%Y-%m-%d %H:%M:%S.%f")
        iso_time = insp_dt.isoformat()
        wafer_key: int = int(insp["wafer_key"][0])

        batches = [batch async for batch in upstream.stream(iso_time, wafer_key)]
        offset_batches = [
            batch async for batch in upstream.stream(iso_time, wafer_key, offset=3)
        ]
        beyond_batches = [
            batch
            async for batch in upstream.stream(iso_time, wafer_key, offset=999_999)
        ]

        all_rows = pl.concat(batches)
        offset_rows = pl.concat(offset_batches)

        assert len(offset_rows) == len(all_rows) - 3
        assert offset_rows["defect_id"][0] == all_rows["defect_id"][3]
        assert beyond_batches == []
    finally:
        teardown_mock_sc_db(db_path)


@pytest.mark.asyncio
async def test_get_inspection_returns_origin_index(tmp_path):
    """Verify get_inspection returns origin_index_x/y from the joined insp_recipe."""
    db_path = str(tmp_path / "test.db")
    create_mock_sc_db(db_path)

    try:
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE insp_recipe SET origin_index_x = 5, origin_index_y = 10")
        conn.commit()
        conn.close()

        upstream = SqliteScUpstream(db_url=f"sqlite:///{db_path}")

        lf = await upstream._read("SELECT * FROM insp_wafer_summary LIMIT 1")
        insp = lf.collect()
        assert len(insp) > 0, "Should have seeded inspection with recipe_key=1"

        insp_time_str: str = insp["inspection_time"][0]
        insp_time = datetime.strptime(insp_time_str, "%Y-%m-%d %H:%M:%S.%f")
        wafer_key: int = int(insp["wafer_key"][0])

        record = await upstream.get_inspection(
            inspection_time=insp_time, wafer_key=wafer_key
        )
        assert record is not None, "get_inspection should return a record"
        assert record.origin_index_x == 5, (
            f"Expected origin_index_x=5, got {record.origin_index_x}"
        )
        assert record.origin_index_y == 10, (
            f"Expected origin_index_y=10, got {record.origin_index_y}"
        )
    finally:
        teardown_mock_sc_db(db_path)


def test_geometry_from_inspection():
    """Verify _geometry_from_inspection returns all 11 expected keys."""
    record = ScInspectionRecord(
        inspection_time=datetime(2026, 5, 26, 8, 0, 0, 0),
        wafer_key=1,
        lot_id="LOT-001",
        wafer_id="WAF-001",
        center_x=150_000_000,
        center_y=150_000_000,
        origin_x=145_000_000,
        origin_y=145_000_000,
        die_size_x=8_000_000,
        die_size_y=5_000_000,
        origin_index_x=5,
        origin_index_y=10,
        device="DEVICE-A",
    )

    result = _geometry_from_inspection(record)

    expected_keys = {
        "center_x",
        "center_y",
        "origin_x",
        "origin_y",
        "die_size_x",
        "die_size_y",
        "origin_index_x",
        "origin_index_y",
        "wafer_id",
        "lot_id",
        "device",
    }
    assert set(result.keys()) == expected_keys, (
        f"Expected keys {expected_keys}, got {set(result.keys())}"
    )
    assert result["center_x"] == 150_000_000
    assert result["center_y"] == 150_000_000
    assert result["origin_x"] == 145_000_000
    assert result["origin_y"] == 145_000_000
    assert result["die_size_x"] == 8_000_000
    assert result["die_size_y"] == 5_000_000
    assert result["origin_index_x"] == 5
    assert result["origin_index_y"] == 10
    assert result["wafer_id"] == "WAF-001"
    assert result["lot_id"] == "LOT-001"
    assert result["device"] == "DEVICE-A"
