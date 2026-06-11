"""Tests for proto_adapter — DataFrame-based make_wafer_map_response_pb."""

from __future__ import annotations

import inspect

import polars as pl
import pytest

from app.modules.sc import proto_adapter
from app.modules.sc.proto_adapter import make_class_list_pb, make_wafer_map_response_pb
from proto_stubs.sc.v1 import sample_pb2


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_df(n: int, *, seed: int = 0) -> pl.DataFrame:
    """Build a synthetic DataFrame with all required columns."""
    import math

    random = __import__("random")
    random.seed(seed)
    return pl.DataFrame(
        {
            "defect_id": list(range(1, n + 1)),
            "wafer_x": [int(math.cos(i * 2.39996) * (i + 1) * 10_000_000) for i in range(n)],
            "wafer_y": [int(math.sin(i * 2.39996) * (i + 1) * 10_000_000) for i in range(n)],
            "die_x": [i * 1000 for i in range(n)],
            "die_y": [i * 500 for i in range(n)],
            "reticle_x": [i * 2000 for i in range(n)],
            "reticle_y": [i * 1000 for i in range(n)],
            "class_number": [i % 3 for i in range(n)],
            "rough_bin": [i % 5 for i in range(n)],
            "has_review": [i % 2 for i in range(n)],
        }
    )


def _parse(body: bytes) -> sample_pb2.WaferMapResponse:
    msg = sample_pb2.WaferMapResponse()
    msg.ParseFromString(body)
    return msg


def test_make_class_list_groups_defect_ids() -> None:
    df = pl.DataFrame(
        {
            "defect_id": [101, 102, 103],
            "class_number": [1, 1, 2],
            "rough_bin": [4, 5, 4],
            "predicted_label": ["scratch", "clean", "scratch"],
            "label": ["review", None, "review"],
        }
    )

    msg = sample_pb2.ClassList()
    msg.ParseFromString(make_class_list_pb(df))

    assert msg.class_numbers["1"].count == 2
    assert list(msg.class_numbers["1"].defect_ids) == [101, 102]
    assert list(msg.rough_bins["4"].defect_ids) == [101, 103]
    assert list(msg.prediction["scratch"].defect_ids) == [101, 103]
    assert list(msg.labels["review"].defect_ids) == [101, 103]
    assert list(msg.labels["__unlabeled__"].defect_ids) == [102]


def test_make_class_list_groups_missing_predictions_as_unlabeled() -> None:
    df = pl.DataFrame(
        {
            "defect_id": [101, 102],
            "class_number": [1, 1],
            "rough_bin": [4, 4],
            "predicted_label": ["scratch", None],
            "label": ["review", "review"],
        }
    )

    msg = sample_pb2.ClassList()
    msg.ParseFromString(make_class_list_pb(df))

    assert list(msg.prediction["__unlabeled__"].defect_ids) == [102]


# ── DataFrame-based WaferMapResponse tests ─────────────────────────────────


class TestMakeWaferMapResponsePb:
    def test_basic_roundtrip(self) -> None:
        """DataFrame roundtrip: wafer_key, total, point counts correct."""
        n = 10
        df = _make_df(n)
        body = make_wafer_map_response_pb(df, wafer_key=42)
        msg = _parse(body)

        assert msg.wafer_key == 42
        assert msg.total == n
        assert len(msg.wafer_points) == n * 6
        assert len(msg.die_points) == n * 6
        assert len(msg.reticle_points) == n * 6

    def test_deterministic(self) -> None:
        """Same DataFrame twice -> same protobuf bytes."""
        df = _make_df(5)
        call1 = make_wafer_map_response_pb(df, wafer_key=1)
        call2 = make_wafer_map_response_pb(df, wafer_key=1)
        assert call1 == call2

    def test_wafer_key_different(self) -> None:
        """Different wafer_key → different bytes."""
        df = _make_df(3)
        r1 = make_wafer_map_response_pb(df, wafer_key=1)
        r2 = make_wafer_map_response_pb(df, wafer_key=2)
        assert r1 != r2

    def test_empty_dataframe(self) -> None:
        """Empty DataFrame → zero points, empty arrays."""
        df = pl.DataFrame(
            {
                "defect_id": [],
                "wafer_x": [],
                "wafer_y": [],
                "die_x": [],
                "die_y": [],
                "reticle_x": [],
                "reticle_y": [],
                "class_number": [],
                "rough_bin": [],
                "has_review": [],
            },
            schema={
                "defect_id": pl.Int32,
                "wafer_x": pl.Int32,
                "wafer_y": pl.Int32,
                "die_x": pl.Int32,
                "die_y": pl.Int32,
                "reticle_x": pl.Int32,
                "reticle_y": pl.Int32,
                "class_number": pl.Int32,
                "rough_bin": pl.Int32,
                "has_review": pl.Int32,
            },
        )
        body = make_wafer_map_response_pb(df, wafer_key=0)
        msg = _parse(body)

        assert msg.total == 0
        assert len(msg.wafer_points) == 0
        assert len(msg.die_points) == 0
        assert len(msg.reticle_points) == 0

    def test_missing_columns_raises(self) -> None:
        """Missing required column → ValueError."""
        df = pl.DataFrame({"defect_id": [1], "wafer_x": [100]})
        with pytest.raises(ValueError):
            make_wafer_map_response_pb(df, wafer_key=0)

    def test_die_xy_preserved(self) -> None:
        """Pre-computed die_x/die_y values pass through unchanged."""
        df = pl.DataFrame(
            {
                "defect_id": [1],
                "wafer_x": [50_000_000],
                "wafer_y": [30_000_000],
                "die_x": [123],
                "die_y": [456],
                "reticle_x": [1000],
                "reticle_y": [2000],
                "class_number": [0],
                "rough_bin": [1],
                "has_review": [0],
            }
        )
        body = make_wafer_map_response_pb(df, wafer_key=0)
        msg = _parse(body)

        die_vals = list(msg.die_points)
        assert die_vals[0] == 123  # die_x
        assert die_vals[1] == 456  # die_y

    def test_reticle_xy_preserved(self) -> None:
        """Pre-computed reticle coordinates pass through unchanged."""
        df = pl.DataFrame(
            {
                "defect_id": [1],
                "wafer_x": [50_000_000],
                "wafer_y": [30_000_000],
                "die_x": [1000],
                "die_y": [2000],
                "reticle_x": [7_777_777],
                "reticle_y": [8_888_888],
                "class_number": [0],
                "rough_bin": [1],
                "has_review": [0],
            }
        )
        body = make_wafer_map_response_pb(df, wafer_key=0)
        msg = _parse(body)

        ret_vals = list(msg.reticle_points)
        assert ret_vals[0] == 7_777_777
        assert ret_vals[1] == 8_888_888

    def test_sampled_reduces_point_count(self) -> None:
        """Sampled=True with small target_resolution caps point count."""
        n = 100
        df = _make_df(n)
        body = make_wafer_map_response_pb(
            df,
            wafer_key=0,
            sampled=True,
            target_resolution=10,
            include_reticle_points=True,
        )
        msg = _parse(body)

        assert msg.is_sampled is True
        assert msg.total == n

        max_allowed = 10 * 10
        wafer_count = len(msg.wafer_points) // 6
        die_count = len(msg.die_points) // 6
        reticle_count = len(msg.reticle_points) // 6

        assert wafer_count > 0
        assert wafer_count <= max_allowed
        assert die_count > 0
        assert die_count <= max_allowed
        assert reticle_count > 0
        assert reticle_count <= max_allowed

    def test_unsampled_returns_all(self) -> None:
        """sampled=False → all points included."""
        n = 50
        df = _make_df(n)
        body = make_wafer_map_response_pb(
            df, wafer_key=0, sampled=False, include_reticle_points=True
        )
        msg = _parse(body)

        assert len(msg.wafer_points) // 6 == n
        assert len(msg.die_points) // 6 == n
        assert len(msg.reticle_points) // 6 == n

    def test_single_defect_all_maps(self) -> None:
        """Single-defect input appears in all three map types."""
        df = pl.DataFrame(
            {
                "defect_id": [1],
                "wafer_x": [0],
                "wafer_y": [0],
                "die_x": [0],
                "die_y": [0],
                "reticle_x": [0],
                "reticle_y": [0],
                "class_number": [0],
                "rough_bin": [0],
                "has_review": [0],
            }
        )
        body = make_wafer_map_response_pb(
            df,
            wafer_key=0,
            sampled=True,
            target_resolution=600,
            include_reticle_points=True,
        )
        msg = _parse(body)

        assert msg.total == 1
        assert len(msg.wafer_points) == 6
        assert len(msg.die_points) == 6
        assert len(msg.reticle_points) == 6

    def test_zoom_filter(self) -> None:
        """Zoom params filter points by wafer coordinate bounding box."""
        df = pl.DataFrame(
            {
                "defect_id": [1, 2, 3, 4],
                "wafer_x": [0, 100, 200, 300],
                "wafer_y": [0, 50, 100, 150],
                "die_x": [0, 0, 0, 0],
                "die_y": [0, 0, 0, 0],
                "reticle_x": [0, 0, 0, 0],
                "reticle_y": [0, 0, 0, 0],
                "class_number": [0, 0, 0, 0],
                "rough_bin": [0, 0, 0, 0],
                "has_review": [0, 0, 0, 0],
            }
        )
        body = make_wafer_map_response_pb(
            df, wafer_key=0, zoom_x=100, zoom_y=50, zoom_w=100, zoom_h=50
        )
        msg = _parse(body)

        assert msg.total == 4  # total reports original count
        # Only defect_ids 2 (100,50) and 3 (200,100) should be in zoom region
        # Actually: zoom_x=100, zoom_w=100 → x in [100,200]
        #           zoom_y=50, zoom_h=50 → y in [50,100]
        # defect_id 2: (100,50) ✓, defect_id 3: (200,100) ✓
        wafer_pts = list(msg.wafer_points)
        assert len(wafer_pts) == 2 * 6  # 2 points
        # Check defect IDs in wafer points (every 6th element starting at index 2)
        defect_ids = [wafer_pts[i] for i in range(2, len(wafer_pts), 6)]
        assert set(defect_ids) == {2, 3}

    def test_die_mode_filters_die_coordinates_and_only_returns_die_points(self) -> None:
        df = pl.DataFrame(
            {
                "defect_id": [1, 2],
                "wafer_x": [100_000, 200_000],
                "wafer_y": [100_000, 200_000],
                "die_x": [10, 90],
                "die_y": [20, 90],
                "reticle_x": [1_010, 1_090],
                "reticle_y": [2_020, 2_090],
                "class_number": [0, 0],
                "rough_bin": [0, 0],
                "has_review": [0, 0],
            }
        )

        body = make_wafer_map_response_pb(
            df,
            wafer_key=0,
            map_mode="die",
            zoom_x=0,
            zoom_y=0,
            zoom_w=50,
            zoom_h=50,
        )
        msg = _parse(body)

        assert list(msg.wafer_points) == []
        assert list(msg.reticle_points) == []
        assert list(msg.die_points) == [10, 20, 1, 0, 0, 0]

    def test_zoom_no_match(self) -> None:
        """Zoom that matches nothing → empty point arrays."""
        df = _make_df(5)
        body = make_wafer_map_response_pb(
            df, wafer_key=0, zoom_x=999_999_999, zoom_y=0, zoom_w=1, zoom_h=1
        )
        msg = _parse(body)

        assert msg.total == 5
        assert len(msg.wafer_points) == 0
        assert len(msg.die_points) == 0

    def test_null_class_number(self) -> None:
        """Null class_number should be packed as -1."""
        df = pl.DataFrame(
            {
                "defect_id": [1],
                "wafer_x": [0],
                "wafer_y": [0],
                "die_x": [0],
                "die_y": [0],
                "reticle_x": [0],
                "reticle_y": [0],
                "class_number": [None],
                "rough_bin": [0],
                "has_review": [0],
            }
        )
        body = make_wafer_map_response_pb(df, wafer_key=0)
        msg = _parse(body)

        # wafer_points: [x, y, defect_id, class_number, rough_bin, has_review]
        wafer_vals = list(msg.wafer_points)
        assert wafer_vals[3] == -1  # class_number position

    def test_no_reticle_when_disabled(self) -> None:
        """include_reticle_points=False → empty reticle_points."""
        df = _make_df(5)
        body = make_wafer_map_response_pb(
            df, wafer_key=0, include_reticle_points=False
        )
        msg = _parse(body)

        assert len(msg.reticle_points) == 0
        assert len(msg.wafer_points) > 0
        assert len(msg.die_points) > 0

    def test_geometry_included(self) -> None:
        """include_geometry=True sets geometry fields."""
        df = _make_df(1)
        body = make_wafer_map_response_pb(
            df,
            wafer_key=0,
            include_geometry=True,
            wafer_radius_nm=100_000_000,
            center_x=10,
            center_y=20,
            origin_x=30,
            origin_y=40,
            die_size_x=5000,
            die_size_y=6000,
        )
        msg = _parse(body)

        geo = msg.geometry
        assert geo.wafer_radius_nm == 100_000_000
        assert geo.center_x == 10
        assert geo.center_y == 20
        assert geo.origin_x == 30
        assert geo.origin_y == 40
        assert geo.die_size_x == 5000
        assert geo.die_size_y == 6000

    def test_geometry_omitted(self) -> None:
        """include_geometry=False → geometry fields are defaults."""
        df = _make_df(1)
        body = make_wafer_map_response_pb(
            df, wafer_key=0, include_geometry=False
        )
        msg = _parse(body)

        assert msg.geometry.wafer_radius_nm == 0
        assert msg.geometry.center_x == 0
        assert msg.geometry.center_y == 0

    def test_reticle_die_counts(self) -> None:
        """reticle_x_die_count and reticle_y_die_count are set in message."""
        df = _make_df(1)
        body = make_wafer_map_response_pb(
            df, wafer_key=0, reticle_x_die_count=7, reticle_y_die_count=8
        )
        msg = _parse(body)

        assert msg.reticle_x_die_count == 7
        assert msg.reticle_y_die_count == 8

    def test_point_packing_6_ints_per_point(self) -> None:
        """Each point packs exactly 6 values: [x, y, defect_id, class_number, rough_bin, has_review]."""
        df = pl.DataFrame(
            {
                "defect_id": [42],
                "wafer_x": [100],
                "wafer_y": [200],
                "die_x": [10],
                "die_y": [20],
                "reticle_x": [1000],
                "reticle_y": [2000],
                "class_number": [3],
                "rough_bin": [5],
                "has_review": [1],
            }
        )
        body = make_wafer_map_response_pb(df, wafer_key=0)
        msg = _parse(body)

        # Wafer points
        expected_wafer = [100, 200, 42, 3, 5, 1]
        assert list(msg.wafer_points) == expected_wafer

        # Die points
        expected_die = [10, 20, 42, 3, 5, 1]
        assert list(msg.die_points) == expected_die

        # Reticle points
        expected_reticle = [1000, 2000, 42, 3, 5, 1]
        assert list(msg.reticle_points) == expected_reticle

    # ── Reticle formula tests (adapted to DataFrame) ──────────────────────

    def test_reticle_deterministic(self) -> None:
        """Same input twice -> same output (no PRNG variation)."""
        df = pl.DataFrame(
            {
                "defect_id": [42],
                "wafer_x": [6_500_000],
                "wafer_y": [12_000_000],
                "die_x": [500_000],
                "die_y": [0],
                "reticle_x": [36_500_000],
                "reticle_y": [0],
                "class_number": [0],
                "rough_bin": [0],
                "has_review": [0],
            }
        )
        call1 = make_wafer_map_response_pb(df, wafer_key=1)
        call2 = make_wafer_map_response_pb(df, wafer_key=1)
        assert call1 == call2

    def test_reticle_does_not_use_stable_unit_interval(self) -> None:
        """Verify _stable_unit_interval is NOT called in make_wafer_map_response_pb."""
        source = inspect.getsource(proto_adapter.make_wafer_map_response_pb)
        assert (
            "_stable_unit_interval" not in source
        ), "make_wafer_map_response_pb still uses PRNG!"
