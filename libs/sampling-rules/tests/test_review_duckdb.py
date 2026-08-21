from __future__ import annotations

import duckdb
import pyarrow as pa

from sampling_rules import (
    ClusterCountRule,
    DuckDbSamplingSource,
    ExcludeClassCodesRule,
    FinalClassDistributionRule,
    FinalClassTarget,
    LargeDefectPercentageRule,
    PerDieLimitRule,
    PerWaferLimitRule,
    RandomCountRule,
    Rounding,
    RepeaterCountRule,
    RequireImageRule,
    ReviewSamplingProgram,
    SizeField,
    SizeRangeRule,
    execute_duckdb_review_sampling,
)


def test_executes_combined_review_rules_over_arrow_without_row_materialization() -> (
    None
):
    connection = duckdb.connect(":memory:")
    connection.register(
        "candidates",
        pa.table(
            {
                "map_id": list(range(12)),
                "inspection_time": ["2026-08-19T10:00:00+08:00"] * 12,
                "wafer_key": [1] * 6 + [2] * 6,
                "index_x": [0, 0, 1, 1, 2, 2] * 2,
                "index_y": [0] * 12,
                "cluster_id": [1, 1, 2, 2, 0, 0] * 2,
                "repeater_id": [0, 7, 0, 8, 7, 8] * 2,
                "class_number": [1, 1, 2, 2, 99, 1] * 2,
                "images": [1, 1, 1, 0, 1, 1] * 2,
                "size_d": [5, 6, 7, 8, 9, 10] * 2,
            }
        ),
    )
    program = ReviewSamplingProgram(
        rules=(
            ExcludeClassCodesRule(class_codes=(99,)),
            RequireImageRule(),
            SizeRangeRule(size_field=SizeField.DIAMETER, minimum=5, maximum=10),
            ClusterCountRule(count=4),
            RepeaterCountRule(count=4),
            RandomCountRule(count=2),
            PerDieLimitRule(limit=1),
            PerWaferLimitRule(limit=3),
        )
    )

    execution = execute_duckdb_review_sampling(
        connection,
        DuckDbSamplingSource.relation(
            "candidates",
            identity_field="map_id",
            output_field="defect_id",
        ),
        program=program,
        seed=42,
        batch_rows=2,
    )
    selected_ids = execution.reader.read_all()["defect_id"].to_pylist()
    selected = connection.execute(
        "SELECT * FROM candidates WHERE map_id = ANY(?)",
        [selected_ids],
    ).to_arrow_table()

    assert len(selected_ids) <= 6
    assert selected["class_number"].to_pylist().count(99) == 0
    assert all(selected["images"].to_pylist())
    for wafer_key in (1, 2):
        assert selected["wafer_key"].to_pylist().count(wafer_key) <= 3
    die_keys = list(
        zip(
            selected["wafer_key"].to_pylist(),
            selected["index_x"].to_pylist(),
            selected["index_y"].to_pylist(),
            strict=True,
        )
    )
    assert len(die_keys) == len(set(die_keys))


def test_executes_limit_and_selector_in_declared_order() -> None:
    connection = duckdb.connect(":memory:")
    connection.register(
        "candidates",
        pa.table(
            {
                "map_id": list(range(10_000)),
                "inspection_time": ["2026-08-20T10:00:00+08:00"] * 10_000,
                "wafer_key": [1] * 10_000,
                "size_d": [200] * 10_000,
            }
        ),
    )
    source = DuckDbSamplingSource.relation(
        "candidates",
        identity_field="map_id",
        output_field="defect_id",
    )
    limit = PerWaferLimitRule(limit=200)
    take_large = LargeDefectPercentageRule(
        percentage=10,
        rounding=Rounding.FLOOR,
        size_field=SizeField.DIAMETER,
        minimum=100,
    )

    limit_then_take = execute_duckdb_review_sampling(
        connection,
        source,
        program=ReviewSamplingProgram(rules=(limit, take_large)),
        seed=42,
        batch_rows=512,
    ).reader.read_all()
    take_then_limit = execute_duckdb_review_sampling(
        connection,
        source,
        program=ReviewSamplingProgram(rules=(take_large, limit)),
        seed=42,
        batch_rows=512,
    ).reader.read_all()

    assert limit_then_take.num_rows == 20
    assert take_then_limit.num_rows == 200


def test_executes_final_class_distribution_with_exact_largest_remainder_quotas() -> (
    None
):
    connection = duckdb.connect(":memory:")
    connection.register(
        "candidates",
        pa.table(
            {
                "map_id": list(range(18)),
                "final_class": ["Scratch"] * 8 + ["Particle"] * 7 + [None] * 3,
            }
        ),
    )

    execution = execute_duckdb_review_sampling(
        connection,
        DuckDbSamplingSource.relation(
            "candidates",
            identity_field="map_id",
            output_field="defect_id",
        ),
        program=ReviewSamplingProgram(
            rules=(
                FinalClassDistributionRule(
                    count=10,
                    targets=(
                        FinalClassTarget(value="Scratch", percentage=50),
                        FinalClassTarget(value="Particle", percentage=30),
                        FinalClassTarget(value=None, percentage=20),
                    ),
                ),
            )
        ),
        seed=23,
        batch_rows=3,
    )
    selected_ids = execution.reader.read_all()["defect_id"].to_pylist()
    selected_classes = connection.execute(
        "SELECT final_class FROM candidates WHERE map_id = ANY(?)",
        [selected_ids],
    ).fetchall()

    assert selected_classes.count(("Scratch",)) == 5
    assert selected_classes.count(("Particle",)) == 3
    assert selected_classes.count((None,)) == 2


def test_excluded_class_codes_keep_unclassified_defects_eligible() -> None:
    connection = duckdb.connect(":memory:")
    connection.register(
        "candidates",
        pa.table(
            {
                "map_id": [1, 2, 3],
                "class_number": [None, 99, 1],
            }
        ),
    )

    execution = execute_duckdb_review_sampling(
        connection,
        DuckDbSamplingSource.relation(
            "candidates",
            identity_field="map_id",
            output_field="defect_id",
        ),
        program=ReviewSamplingProgram(
            rules=(
                ExcludeClassCodesRule(class_codes=(99,)),
                RandomCountRule(count=10),
            )
        ),
        seed=7,
        batch_rows=10,
    )

    assert set(execution.reader.read_all()["defect_id"].to_pylist()) == {1, 3}
