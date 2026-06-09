from __future__ import annotations

import math

import polars as pl

from proto_stubs.sc.v1 import sample_pb2

from app.modules.sc.proto_adapter import make_wafer_map_response_pb


def _build_synthetic_df(count: int, wafer_radius_nm: int = 150_000_000) -> pl.DataFrame:
    defect_ids: list[int] = []
    wafer_xs: list[int] = []
    wafer_ys: list[int] = []
    rough_bins: list[int] = []
    class_numbers: list[int] = []

    for i in range(count):
        angle = i * 2.39996
        radius = wafer_radius_nm * math.sqrt(i + 1) / math.sqrt(count)
        defect_ids.append(i + 1)
        wafer_xs.append(int(radius * math.cos(angle)))
        wafer_ys.append(int(radius * math.sin(angle)))
        rough_bins.append(i % 5)
        class_numbers.append(i % 3)

    return pl.DataFrame(
        {
            "defect_id": defect_ids,
            "wafer_x": wafer_xs,
            "wafer_y": wafer_ys,
            "die_x": wafer_xs,
            "die_y": wafer_ys,
            "reticle_x": wafer_xs,
            "reticle_y": wafer_ys,
            "class_number": class_numbers,
            "rough_bin": rough_bins,
            "has_review": [0] * count,
        }
    )


def test_adaptive_per_map_sampling_limits_point_count() -> None:
    target_resolution = 10
    wafer_radius_nm = 150_000_000
    df = _build_synthetic_df(100, wafer_radius_nm=wafer_radius_nm)

    body = make_wafer_map_response_pb(
        df,
        wafer_key=0,
        wafer_radius_nm=wafer_radius_nm,
        die_size_x=26_000_000,
        die_size_y=33_000_000,
        sampled=True,
        target_resolution=target_resolution,
        include_reticle_points=True,
    )

    msg = sample_pb2.WaferMapResponse()
    msg.ParseFromString(body)

    assert msg.is_sampled is True
    assert msg.total == 100

    max_allowed = target_resolution * target_resolution
    wafer_count = len(msg.wafer_points) // 6
    die_count = len(msg.die_points) // 6
    reticle_count = len(msg.reticle_points) // 6

    assert wafer_count > 0, "wafer_points must not be empty"
    assert die_count > 0, "die_points must not be empty"
    assert reticle_count > 0, "reticle_points must not be empty when include_reticle_points=True"

    assert wafer_count <= max_allowed, (
        f"wafer_count={wafer_count} exceeds target_resolution^2={max_allowed}"
    )
    assert die_count <= max_allowed, (
        f"die_count={die_count} exceeds target_resolution^2={max_allowed}"
    )
    assert reticle_count <= max_allowed, (
        f"reticle_count={reticle_count} exceeds target_resolution^2={max_allowed}"
    )


def test_reticle_non_empty_when_included() -> None:
    df = _build_synthetic_df(50)

    body = make_wafer_map_response_pb(
        df,
        wafer_key=0,
        sampled=False,
        include_reticle_points=True,
    )

    msg = sample_pb2.WaferMapResponse()
    msg.ParseFromString(body)

    reticle_count = len(msg.reticle_points) // 6
    assert reticle_count > 0, "reticle_points must be non-empty when include_reticle_points=True"


def test_unsampled_returns_all_points() -> None:
    df = _build_synthetic_df(50)

    body = make_wafer_map_response_pb(
        df,
        wafer_key=0,
        sampled=False,
        include_reticle_points=True,
    )

    msg = sample_pb2.WaferMapResponse()
    msg.ParseFromString(body)

    wafer_count = len(msg.wafer_points) // 6
    die_count = len(msg.die_points) // 6
    reticle_count = len(msg.reticle_points) // 6

    assert wafer_count == 50, f"wafer_count={wafer_count}, expected 50"
    assert die_count == 50, f"die_count={die_count}, expected 50"
    assert reticle_count == 50, f"reticle_count={reticle_count}, expected 50"


def test_single_defect_every_map_has_it() -> None:
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
        die_size_x=10_000,
        die_size_y=10_000,
    )

    msg = sample_pb2.WaferMapResponse()
    msg.ParseFromString(body)

    assert msg.total == 1
    assert len(msg.wafer_points) == 6
    assert len(msg.die_points) == 6
    assert len(msg.reticle_points) == 6
