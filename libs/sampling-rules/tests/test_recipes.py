from __future__ import annotations

import pytest

from sampling_rules import (
    InvalidSamplingRuleError,
    Rounding,
    adder_count_program,
    clipped_log10_quota,
    clustered_count_program,
    clustered_ratio_program,
    per_die_cap_program,
    prediction_log_quota_program,
    sample,
)


def test_clustered_count_recipe_selects_only_clustered_rows() -> None:
    rows = [
        {"id": index, "dynamic_cluster_id": cluster_id}
        for index, cluster_id in enumerate([0, 1, 1, 2, 2, 0])
    ]

    selected = sample(rows, program=clustered_count_program(3))

    assert len(selected) == 3
    assert all(row["dynamic_cluster_id"] > 0 for row in selected)


def test_clustered_ratio_recipe_samples_percentage_and_excludes_noise() -> None:
    rows = [{"id": index, "dynamic_cluster": int(index < 10)} for index in range(20)]

    selected = sample(
        rows,
        program=clustered_ratio_program(50, rounding=Rounding.NEAREST),
    )

    assert len(selected) == 5
    assert all(row["dynamic_cluster"] == 1 for row in selected)


def test_adder_count_recipe_selects_only_adders() -> None:
    rows = [{"id": index, "dynamic_adder": int(index % 2 == 0)} for index in range(10)]

    selected = sample(rows, program=adder_count_program(3))

    assert len(selected) == 3
    assert all(row["dynamic_adder"] == 1 for row in selected)


def test_per_die_recipe_caps_each_die_independently() -> None:
    rows = [{"id": index, "index_x": index // 8, "index_y": 0} for index in range(16)]

    selected = sample(
        rows,
        program=per_die_cap_program(
            5,
            die_x_field="index_x",
            die_y_field="index_y",
        ),
    )

    assert len(selected) == 10
    assert sum(row["index_x"] == 0 for row in selected) == 5
    assert sum(row["index_x"] == 1 for row in selected) == 5


@pytest.mark.parametrize(
    ("population", "rounding", "expected"),
    [
        (1, Rounding.NEAREST, 3),
        (1_000, Rounding.NEAREST, 3),
        (50_000, Rounding.FLOOR, 4),
        (50_000, Rounding.NEAREST, 5),
        (50_000, Rounding.CEIL, 5),
        (10**12, Rounding.NEAREST, 10),
    ],
)
def test_clipped_log10_prediction_quota(
    population: int,
    rounding: Rounding,
    expected: int,
) -> None:
    assert (
        clipped_log10_quota(
            population,
            minimum=3,
            maximum=10,
            rounding=rounding,
        )
        == expected
    )


def test_prediction_recipe_builds_and_applies_population_targets() -> None:
    populations = {"scratch": 1, "particle": 1_000, "residue": 50_000}
    rows = [
        {"id": f"{prediction}-{index}", "prediction_label": prediction}
        for prediction in populations
        for index in range(12)
    ]

    selected = sample(
        rows,
        program=prediction_log_quota_program(
            populations,
            prediction_field="prediction_label",
            minimum=3,
            maximum=10,
            rounding=Rounding.CEIL,
        ),
    )

    assert sum(row["prediction_label"] == "scratch" for row in selected) == 3
    assert sum(row["prediction_label"] == "particle" for row in selected) == 3
    assert sum(row["prediction_label"] == "residue" for row in selected) == 5


def test_prediction_recipe_rejects_an_empty_population() -> None:
    with pytest.raises(InvalidSamplingRuleError, match="positive population"):
        prediction_log_quota_program(
            {"scratch": 0},
            prediction_field="prediction_label",
            minimum=3,
            maximum=10,
            rounding=Rounding.NEAREST,
        )


def test_prediction_recipe_rejects_a_negative_population() -> None:
    with pytest.raises(
        InvalidSamplingRuleError,
        match="populations must be non-negative integers",
    ):
        prediction_log_quota_program(
            {"scratch": -1, "particle": 1_000},
            prediction_field="prediction_label",
            minimum=3,
            maximum=10,
            rounding=Rounding.CEIL,
        )
