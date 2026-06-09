from __future__ import annotations

import polars as pl

from app.modules.sc.proto_adapter import _downsample_grouped
from app.modules.sc.app.services.sc_plot_points_service import _apply_sample_filters


def _imbalanced_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "defect_id": list(range(1, 61)),
            "wafer_x": [(i * 1000) for i in range(60)],
            "wafer_y": [(i * 500) for i in range(60)],
            "class_number": [0] * 50 + [1] * 8 + [2] * 2,
            "rough_bin": [0] * 30 + [1] * 15 + [2] * 10 + [3] * 5,
            "has_review": [0] * 60,
        }
    )


class TestDownsampleGrouped:
    def test_preserves_minority_classes(self) -> None:
        df = _imbalanced_df()
        result = _downsample_grouped(df, "wafer_x", "wafer_y", grid_size=10_000, group_col="class_number")

        unique_classes = set(result["class_number"].to_list())
        assert 2 in unique_classes, "minority class 2 should be preserved"
        assert 1 in unique_classes, "minority class 1 should be preserved"
        assert 0 in unique_classes, "majority class 0 should be preserved"

    def test_multiple_class_numbers_in_output(self) -> None:
        df = _imbalanced_df()
        result = _downsample_grouped(df, "wafer_x", "wafer_y", grid_size=5_000, group_col="class_number")

        classes = result["class_number"].to_list()
        unique_classes = set(classes)
        assert len(unique_classes) >= 2

    def test_ungrouped_equivalent_when_single_class(self) -> None:
        df = pl.DataFrame(
            {
                "defect_id": [1, 2, 3, 4, 5],
                "wafer_x": [0, 10, 20, 30, 40],
                "wafer_y": [0, 10, 20, 30, 40],
                "class_number": [1, 1, 1, 1, 1],
            }
        )
        result = _downsample_grouped(df, "wafer_x", "wafer_y", grid_size=100, group_col="class_number")
        assert len(result) <= len(df)

    def test_null_group_values_preserved(self) -> None:
        df = pl.DataFrame(
            {
                "defect_id": [1, 2, 3],
                "wafer_x": [0, 10, 20],
                "wafer_y": [0, 10, 20],
                "class_number": [None, 1, 1],
            }
        )
        result = _downsample_grouped(df, "wafer_x", "wafer_y", grid_size=1, group_col="class_number")
        assert len(result) > 0

    def test_empty_dataframe(self) -> None:
        df = pl.DataFrame(
            schema={
                "defect_id": pl.Int64,
                "wafer_x": pl.Int64,
                "wafer_y": pl.Int64,
                "class_number": pl.Int64,
            }
        )
        result = _downsample_grouped(df, "wafer_x", "wafer_y", grid_size=100, group_col="class_number")
        assert len(result) == 0

    def test_zero_grid_size_returns_unchanged(self) -> None:
        df = _imbalanced_df()
        result = _downsample_grouped(df, "wafer_x", "wafer_y", grid_size=0, group_col="class_number")
        assert len(result) == len(df)

    def test_does_not_apply_a_global_point_cap(self) -> None:
        df = _imbalanced_df()
        result = _downsample_grouped(
            df,
            "wafer_x",
            "wafer_y",
            grid_size=1,
            group_col="class_number",
        )
        assert len(result) == len(df)


class TestApplySampleFilters:
    def _make_lf(self) -> pl.LazyFrame:
        return pl.DataFrame(
            {
                "class_number": [0, 1, 0, 2, 1, 0],
                "rough_bin": [0, 0, 1, 2, 1, 0],
                "defect_id": [101, 102, 103, 104, 105, 106],
                "extra_col": [10, 20, 30, 40, 50, 60],
            }
        ).lazy()

    def test_single_filter_reduces_count(self) -> None:
        lf = self._make_lf()
        filtered = _apply_sample_filters(lf, class_number=[1])
        result = filtered.collect()
        assert len(result) == 2
        assert all(v == 1 for v in result["class_number"].to_list())

    def test_and_combination_reduces_further(self) -> None:
        lf = self._make_lf()
        filtered = _apply_sample_filters(lf, class_number=[0, 1], rough_bin=[0])
        result = filtered.collect()
        assert len(result) > 0
        assert len(result) < 6
        for row in result.iter_rows(named=True):
            assert row["class_number"] in (0, 1)
            assert row["rough_bin"] == 0

    def test_and_combination_no_match(self) -> None:
        lf = pl.DataFrame(
            {
                "class_number": [0, 1, 2],
                "rough_bin": [0, 1, 2],
                "defect_id": [1, 2, 3],
            }
        ).lazy()
        filtered = _apply_sample_filters(lf, class_number=[0], rough_bin=[5])
        result = filtered.collect()
        assert len(result) == 0

    def test_empty_filter_list_skipped_nonempty_still_applies(self) -> None:
        lf = self._make_lf()
        filtered = _apply_sample_filters(lf, class_number=[], rough_bin=[0])
        result = filtered.collect()
        assert len(result) == 3
        assert all(v == 0 for v in result["rough_bin"].to_list())

    def test_no_filters_returns_all(self) -> None:
        lf = self._make_lf()
        filtered = _apply_sample_filters(lf)
        result = filtered.collect()
        assert len(result) == 6

    def test_missing_column_skipped_gracefully(self) -> None:
        lf = self._make_lf()
        filtered = _apply_sample_filters(lf, class_number=[1], nonexistent_col=[999])
        result = filtered.collect()
        assert len(result) == 2

    def test_all_columns_missing_returns_unchanged(self) -> None:
        lf = self._make_lf()
        filtered = _apply_sample_filters(lf, nonexistent_a=[1], nonexistent_b=[2])
        result = filtered.collect()
        assert len(result) == 6

    def test_string_filter(self) -> None:
        lf = pl.DataFrame(
            {
                "label": ["scratch", "clean", "scratch", "review"],
                "defect_id": [1, 2, 3, 4],
            }
        ).lazy()
        filtered = _apply_sample_filters(lf, label=["scratch"])
        result = filtered.collect()
        assert len(result) == 2
        assert all(v == "scratch" for v in result["label"].to_list())

    def test_multiple_filters_on_same_column(self) -> None:
        lf = self._make_lf()
        filtered = _apply_sample_filters(lf, class_number=[0, 2])
        result = filtered.collect()
        assert len(result) == 4
        for v in result["class_number"].to_list():
            assert v in (0, 2)
