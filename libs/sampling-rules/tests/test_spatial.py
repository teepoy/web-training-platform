from __future__ import annotations

from typing import cast

import pytest

from sampling_rules import (
    AdderMatchMode,
    ClusterPointRole,
    DynamicAdderConfig,
    DynamicClusterConfig,
    InvalidSamplingRuleError,
    MissingFieldError,
    compute_dynamic_adders,
    compute_dynamic_clusters,
    enrich_rows_with_dynamic_spatial_features,
)


def points(*coordinates: tuple[float, float]) -> list[dict[str, object]]:
    return [
        {"id": index, "wafer_x": x, "wafer_y": y}
        for index, (x, y) in enumerate(coordinates)
    ]


def test_dynamic_adder_matches_within_inclusive_radius() -> None:
    current = points((0, 0), (50_000, 0), (50_001, 0))
    reference = points((0, 0))

    results = compute_dynamic_adders(
        current,
        reference,
        config=DynamicAdderConfig(
            x_field="wafer_x",
            y_field="wafer_y",
            radius=50_000,
            match_mode=AdderMatchMode.ANY_REFERENCE,
        ),
    )

    assert [result.adder for result in results] == [0, 0, 1]
    assert [result.distance for result in results] == [0, 50_000, None]


def test_dynamic_adder_one_to_one_consumes_a_reference_defect() -> None:
    current = points((10, 0), (20, 0))
    reference = points((0, 0))

    results = compute_dynamic_adders(
        current,
        reference,
        config=DynamicAdderConfig(
            x_field="wafer_x",
            y_field="wafer_y",
            radius=100,
            match_mode=AdderMatchMode.ONE_TO_ONE,
        ),
    )

    assert [result.adder for result in results] == [0, 1]
    assert results[0].matched_reference_index == 0
    assert results[1].matched_reference_index is None


def test_dynamic_cluster_labels_core_border_and_noise_points() -> None:
    current = points((0, 0), (100, 0), (200, 0), (1_000, 0))

    results = compute_dynamic_clusters(
        current,
        config=DynamicClusterConfig(
            x_field="wafer_x",
            y_field="wafer_y",
            radius=100,
            minimum_points=3,
        ),
    )

    assert [result.cluster_id for result in results] == [1, 1, 1, 0]
    assert [result.role for result in results] == [
        ClusterPointRole.BORDER,
        ClusterPointRole.CORE,
        ClusterPointRole.BORDER,
        ClusterPointRole.NOISE,
    ]
    assert [result.neighbor_count for result in results] == [2, 3, 2, 1]


def test_dynamic_cluster_ids_are_deterministic_for_multiple_clusters() -> None:
    current = points(
        (0, 0),
        (50, 0),
        (100, 0),
        (1_000, 0),
        (1_050, 0),
        (1_100, 0),
    )
    config = DynamicClusterConfig(
        x_field="wafer_x",
        y_field="wafer_y",
        radius=60,
        minimum_points=2,
    )

    first = compute_dynamic_clusters(current, config=config)
    second = compute_dynamic_clusters(current, config=config)

    assert first == second
    assert [result.cluster_id for result in first] == [1, 1, 1, 2, 2, 2]


def test_enrichment_exposes_dynamic_fields_to_sampling_rules() -> None:
    current = points((0, 0), (100, 0), (200, 0), (1_000, 0))
    reference = points((0, 0))

    enriched = enrich_rows_with_dynamic_spatial_features(
        current,
        reference_rows=reference,
        adder_config=DynamicAdderConfig(
            x_field="wafer_x",
            y_field="wafer_y",
            radius=50,
            match_mode=AdderMatchMode.ANY_REFERENCE,
        ),
        cluster_config=DynamicClusterConfig(
            x_field="wafer_x",
            y_field="wafer_y",
            radius=100,
            minimum_points=3,
        ),
    )

    assert [row["dynamic_adder"] for row in enriched] == [0, 1, 1, 1]
    assert [row["dynamic_cluster"] for row in enriched] == [1, 1, 1, 0]
    assert [row["dynamic_cluster_id"] for row in enriched] == [1, 1, 1, 0]
    assert enriched[1]["dynamic_cluster_role"] == "core"
    assert enriched[0]["dynamic_adder_distance"] == 0


def test_dynamic_adder_requires_a_selected_reference_layer() -> None:
    with pytest.raises(InvalidSamplingRuleError, match="user-selected reference layer"):
        enrich_rows_with_dynamic_spatial_features(
            points((0, 0)),
            adder_config=DynamicAdderConfig(
                x_field="wafer_x",
                y_field="wafer_y",
                radius=50_000,
                match_mode=AdderMatchMode.ONE_TO_ONE,
            ),
        )


def test_dynamic_adder_rejects_an_unknown_match_mode() -> None:
    with pytest.raises(InvalidSamplingRuleError, match="match_mode"):
        compute_dynamic_adders(
            points((0, 0)),
            points((0, 0)),
            config=DynamicAdderConfig(
                x_field="wafer_x",
                y_field="wafer_y",
                radius=50_000,
                match_mode=cast(AdderMatchMode, "closest"),
            ),
        )


@pytest.mark.parametrize("radius", [0, -1, float("inf"), float("nan")])
def test_dynamic_spatial_radius_must_be_finite_and_positive(radius: float) -> None:
    with pytest.raises(InvalidSamplingRuleError, match="finite positive"):
        compute_dynamic_clusters(
            points((0, 0)),
            config=DynamicClusterConfig(
                x_field="wafer_x",
                y_field="wafer_y",
                radius=radius,
                minimum_points=2,
            ),
        )


def test_dynamic_cluster_requires_at_least_two_points() -> None:
    with pytest.raises(InvalidSamplingRuleError, match="at least two"):
        compute_dynamic_clusters(
            points((0, 0)),
            config=DynamicClusterConfig(
                x_field="wafer_x",
                y_field="wafer_y",
                radius=500_000,
                minimum_points=1,
            ),
        )


def test_dynamic_spatial_coordinates_must_exist_and_be_numeric() -> None:
    with pytest.raises(MissingFieldError, match="wafer_y"):
        compute_dynamic_clusters(
            [{"wafer_x": 0}],
            config=DynamicClusterConfig(
                x_field="wafer_x",
                y_field="wafer_y",
                radius=500_000,
                minimum_points=2,
            ),
        )
