from __future__ import annotations

from datetime import datetime
import io
import sqlite3
import struct
import zipfile

import pytest
from diskcache import Cache

from infra.compose.seed_patch_zips import (
    clear_upstream_metadata_cache,
    create_patch_zips,
    create_review_images,
    load_inspection_seed,
)


INSPECTION_TIME = "2026-08-01 04:00:00.000000"


class _ObjectStore:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> None:
        self.objects[(Bucket, Key)] = (Body, ContentType)


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


@pytest.mark.parametrize(
    ("patch_bit_depth", "png_bit_depth", "reference_count", "difference_count"),
    [
        (8, 8, 1, 1),
        (12, 16, 2, 2),
        (16, 16, 1, 1),
        (16, 16, 2, 2),
    ],
)
def test_patch_seed_uses_native_grayscale_depth_and_multiple_instances(
    patch_bit_depth: int,
    png_bit_depth: int,
    reference_count: int,
    difference_count: int,
) -> None:
    store = _ObjectStore()

    create_patch_zips(
        wafer_key=1,
        inspection_time=datetime(2026, 8, 1, 4, 0),
        total_defects=1,
        s3=store,
        patch_bit_depth=patch_bit_depth,
        reference_count=reference_count,
        difference_count=difference_count,
    )

    archive_bytes, content_type = next(iter(store.objects.values()))
    assert content_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        expected_names = {
            "000001_PatchDefective.png",
            "000001_PatchMask0.png",
            *{
                f"000001_PatchReference{image_id}.png"
                for image_id in range(reference_count)
            },
            *{
                f"000001_PatchDifference{image_id}.png"
                for image_id in range(difference_count)
            },
        }
        assert set(archive.namelist()) == expected_names
        for name in archive.namelist():
            png = archive.read(name)
            width, height, bit_depth, color_type = struct.unpack(">IIBB", png[16:26])
            assert (width, height) == (32, 32)
            if "Mask" in name:
                assert (bit_depth, color_type) == (8, 0)
            else:
                assert (bit_depth, color_type) == (png_bit_depth, 0)


def test_review_seed_uploads_square_pngs_at_upstream_filespec_keys() -> None:
    store = _ObjectStore()

    uploaded = create_review_images(
        wafer_key=1,
        inspection_time=datetime(2026, 8, 1, 4, 0),
        imaged_defects=2,
        images_per_defect=2,
        s3=store,
    )

    assert uploaded == 4
    assert set(store.objects) == {
        ("wafer-review-images", "20260801_040000/1/0000001_1.png"),
        ("wafer-review-images", "20260801_040000/1/0000001_2.png"),
        ("wafer-review-images", "20260801_040000/1/0000002_1.png"),
        ("wafer-review-images", "20260801_040000/1/0000002_2.png"),
    }
    for png, content_type in store.objects.values():
        assert content_type == "image/png"
        width, height, bit_depth, color_type = struct.unpack(">IIBB", png[16:26])
        assert (width, height, bit_depth, color_type) == (256, 256, 8, 2)
