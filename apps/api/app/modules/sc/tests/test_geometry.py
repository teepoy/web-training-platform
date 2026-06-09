from __future__ import annotations

import pytest

from app.modules.sc.domain.geometry import compute_die_and_index


class TestComputeDieAndIndex:
    """Unit tests for compute_die_and_index()."""

    def test_basic_computation(self) -> None:
        wafer_x = 6_500_000
        wafer_y = 12_000_000
        origin_x = -150_000_000
        origin_y = -300_000_000
        die_size_x = 6_000_000
        die_size_y = 8_000_000

        die_x, die_y, index_x, index_y = compute_die_and_index(
            wafer_x=wafer_x,
            wafer_y=wafer_y,
            origin_x=origin_x,
            origin_y=origin_y,
            die_size_x=die_size_x,
            die_size_y=die_size_y,
        )

        assert die_x == 500_000
        assert index_x == 26
        assert die_y == 0
        assert index_y == 39

    def test_zero_die_size_guard(self) -> None:
        wafer_x = 1000
        wafer_y = 2000
        origin_x = 0
        origin_y = 0
        die_size_x = 0
        die_size_y = 0

        result = compute_die_and_index(
            wafer_x=wafer_x,
            wafer_y=wafer_y,
            origin_x=origin_x,
            origin_y=origin_y,
            die_size_x=die_size_x,
            die_size_y=die_size_y,
        )

        assert result == (0, 0, 1000, 2000)

    def test_negative_wafer_coordinates(self) -> None:
        die_x, die_y, index_x, index_y = compute_die_and_index(
            wafer_x=-500,
            wafer_y=-300,
            origin_x=0,
            origin_y=0,
            die_size_x=200,
            die_size_y=200,
        )

        assert die_x == 100
        assert die_y == 100
        assert index_x == -3
        assert index_y == -2

    def test_origin_offset(self) -> None:
        die_x, die_y, index_x, index_y = compute_die_and_index(
            wafer_x=150,
            wafer_y=150,
            origin_x=100,
            origin_y=100,
            die_size_x=50,
            die_size_y=50,
        )

        assert die_x == 0
        assert die_y == 0
        assert index_x == 1
        assert index_y == 1

    def test_negative_die_size_treated_as_one(self) -> None:
        result = compute_die_and_index(
            wafer_x=500,
            wafer_y=500,
            origin_x=0,
            origin_y=0,
            die_size_x=-5,
            die_size_y=-10,
        )

        assert result == (0, 0, 500, 500)
