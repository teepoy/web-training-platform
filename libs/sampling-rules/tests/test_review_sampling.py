from __future__ import annotations

from sampling_rules import (
    ClusterCountRule,
    ClusterPercentageRule,
    ExcludeClassCodesRule,
    FinalClassDistributionRule,
    FinalClassTarget,
    IncludeClassCodesRule,
    LargeDefectCountRule,
    LargeDefectPercentageRule,
    PerClusterLimitRule,
    PerDieLimitRule,
    PerRepeaterLimitRule,
    PerWaferLimitRule,
    REVIEW_SAMPLING_RULE_CATALOG,
    RandomCountRule,
    RandomPercentageRule,
    RepeaterCountRule,
    RepeaterPercentageRule,
    RequireImageRule,
    ReviewSamplingProgram,
    Rounding,
    SizeField,
    SizeRangeRule,
    InvalidSamplingRuleError,
    sample_review,
    validate_review_sampling_program,
)
import pytest


def test_cluster_percentage_selects_from_clustered_defects_only() -> None:
    rows = [
        {"id": index, "cluster_id": cluster_id}
        for index, cluster_id in enumerate([0, 0, 1, 1, 2, 2])
    ]

    selected = sample_review(
        rows,
        program=ReviewSamplingProgram(
            rules=(
                ClusterPercentageRule(
                    percentage=50,
                    rounding=Rounding.NEAREST,
                ),
            )
        ),
        identity_field="id",
        seed=42,
    )

    assert len(selected) == 2
    assert all(int(row["cluster_id"]) > 0 for row in selected)


def test_each_selector_uses_the_previous_step_output() -> None:
    rows = [
        {
            "id": index,
            "cluster_id": 1 if index < 4 else 0,
            "repeater_id": 8 if 4 <= index < 8 else 0,
            "size_d": index + 1,
        }
        for index in range(10)
    ]

    selected = sample_review(
        rows,
        program=ReviewSamplingProgram(
            rules=(
                ClusterCountRule(count=2),
                RepeaterPercentageRule(percentage=50, rounding=Rounding.NEAREST),
                LargeDefectCountRule(
                    count=1,
                    size_field=SizeField.DIAMETER,
                    minimum=9,
                ),
            )
        ),
        identity_field="id",
        seed=7,
    )

    assert selected == []


def test_all_count_and_percentage_selector_types_are_executable() -> None:
    rows = [
        {
            "id": index,
            "cluster_id": 1 if index < 6 else 0,
            "repeater_id": 1 if index >= 4 else 0,
            "area": index + 1,
        }
        for index in range(10)
    ]
    programs = (
        ClusterCountRule(count=2),
        RepeaterCountRule(count=2),
        RandomCountRule(count=2),
        RandomPercentageRule(percentage=20, rounding=Rounding.NEAREST),
        LargeDefectPercentageRule(
            percentage=50,
            rounding=Rounding.NEAREST,
            size_field=SizeField.AREA,
            minimum=7,
        ),
    )

    for rule in programs:
        selected = sample_review(
            rows,
            program=ReviewSamplingProgram(rules=(rule,)),
            identity_field="id",
            seed=11,
        )
        assert len(selected) == 2


def test_eligibility_rules_filter_before_random_selection() -> None:
    rows = [
        {"id": "keep-1", "class_number": 1, "images": 2, "size_d": 5},
        {"id": "keep-2", "class_number": 2, "images": 1, "size_d": 10},
        {"id": "excluded", "class_number": 99, "images": 1, "size_d": 8},
        {"id": "no-image", "class_number": 1, "images": 0, "size_d": 8},
        {"id": "too-small", "class_number": 2, "images": 1, "size_d": 4},
        {"id": "not-included", "class_number": 3, "images": 1, "size_d": 8},
    ]

    selected = sample_review(
        rows,
        program=ReviewSamplingProgram(
            rules=(
                ExcludeClassCodesRule(class_codes=(99,)),
                RequireImageRule(),
                SizeRangeRule(size_field=SizeField.DIAMETER, minimum=5, maximum=10),
                IncludeClassCodesRule(class_codes=(1, 2, 99)),
                RandomCountRule(count=20),
            )
        ),
        identity_field="id",
        seed=3,
    )

    assert {row["id"] for row in selected} == {"keep-1", "keep-2"}


def test_group_caps_apply_in_declared_order() -> None:
    rows = [
        {
            "id": index,
            "inspection_time": "2026-08-19T10:00:00+08:00",
            "wafer_key": 1 + index // 8,
            "index_x": (index % 8) // 4,
            "index_y": 0,
            "cluster_id": 1 + index % 2,
            "repeater_id": 1 + index % 3,
        }
        for index in range(16)
    ]
    caps = (
        PerDieLimitRule(limit=2),
        PerClusterLimitRule(limit=3),
        PerRepeaterLimitRule(limit=2),
        PerWaferLimitRule(limit=4),
    )

    selected = sample_review(
        rows,
        program=ReviewSamplingProgram(rules=(RandomCountRule(count=16), *caps)),
        identity_field="id",
        seed=17,
    )
    reordered = sample_review(
        rows,
        program=ReviewSamplingProgram(
            rules=(RandomCountRule(count=16), *reversed(caps))
        ),
        identity_field="id",
        seed=17,
    )

    assert {row["id"] for row in selected} != {row["id"] for row in reordered}
    for result in (selected, reordered):
        for wafer_key in (1, 2):
            assert sum(row["wafer_key"] == wafer_key for row in result) <= 4
        for index_x in (0, 1):
            for wafer_key in (1, 2):
                assert (
                    sum(
                        row["wafer_key"] == wafer_key and row["index_x"] == index_x
                        for row in result
                    )
                    <= 2
                )
        for cluster_id in (1, 2):
            assert sum(row["cluster_id"] == cluster_id for row in result) <= 3
        for repeater_id in (1, 2, 3):
            assert sum(row["repeater_id"] == repeater_id for row in result) <= 2


def test_pipeline_applies_limit_and_selector_in_declared_order() -> None:
    rows = [
        {
            "id": index,
            "inspection_time": "2026-08-20T10:00:00+08:00",
            "wafer_key": 1,
            "size_d": 200,
        }
        for index in range(10_000)
    ]
    limit = PerWaferLimitRule(limit=200)
    take_large = LargeDefectPercentageRule(
        percentage=10,
        rounding=Rounding.FLOOR,
        size_field=SizeField.DIAMETER,
        minimum=100,
    )

    limit_then_take = sample_review(
        rows,
        program=ReviewSamplingProgram(rules=(limit, take_large)),
        identity_field="id",
        seed=42,
    )
    take_then_limit = sample_review(
        rows,
        program=ReviewSamplingProgram(rules=(take_large, limit)),
        identity_field="id",
        seed=42,
    )

    assert len(limit_then_take) == 20
    assert len(take_then_limit) == 200


def test_final_class_distribution_uses_exact_largest_remainder_quotas() -> None:
    rows = (
        [{"id": f"scratch-{index}", "final_class": "Scratch"} for index in range(6)]
        + [{"id": f"particle-{index}", "final_class": "Particle"} for index in range(6)]
        + [{"id": f"unclassified-{index}", "final_class": None} for index in range(3)]
    )

    selected = sample_review(
        rows,
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
        identity_field="id",
        seed=23,
    )

    assert sum(row["final_class"] == "Scratch" for row in selected) == 5
    assert sum(row["final_class"] == "Particle" for row in selected) == 3
    assert sum(row["final_class"] is None for row in selected) == 2


def test_review_sampling_catalog_declares_all_seventeen_product_rules() -> None:
    assert [descriptor.id for descriptor in REVIEW_SAMPLING_RULE_CATALOG] == [
        "cluster_percentage",
        "repeater_percentage",
        "random_percentage",
        "exclude_class_codes",
        "per_die_limit",
        "cluster_count",
        "repeater_count",
        "random_count",
        "per_cluster_limit",
        "per_repeater_limit",
        "per_wafer_limit",
        "require_image",
        "size_range",
        "include_class_codes",
        "large_defect_percentage",
        "large_defect_count",
        "final_class_distribution",
    ]
    assert (
        len({descriptor.rule_type for descriptor in REVIEW_SAMPLING_RULE_CATALOG}) == 17
    )


def test_review_sampling_program_rejects_duplicates_and_filter_only_programs() -> None:
    with pytest.raises(InvalidSamplingRuleError, match="more than once"):
        validate_review_sampling_program(
            ReviewSamplingProgram(
                rules=(RandomCountRule(count=10), RandomCountRule(count=20))
            )
        )
    with pytest.raises(InvalidSamplingRuleError, match="selector or cap"):
        validate_review_sampling_program(
            ReviewSamplingProgram(rules=(RequireImageRule(),))
        )


def test_all_seventeen_rules_compose_as_one_declared_pipeline() -> None:
    rows = [
        {
            "id": index,
            "inspection_time": "2026-08-19T10:00:00+08:00",
            "wafer_key": 1 + index // 24,
            "index_x": (index // 4) % 3,
            "index_y": index % 2,
            "cluster_id": 1 + index % 4,
            "repeater_id": 1 + index % 5,
            "class_number": 1,
            "images": 1,
            "size_d": 12,
            "final_class": "Scratch",
        }
        for index in range(48)
    ]
    rules = (
        ClusterPercentageRule(percentage=100, rounding=Rounding.FLOOR),
        RepeaterPercentageRule(percentage=100, rounding=Rounding.FLOOR),
        RandomPercentageRule(percentage=100, rounding=Rounding.FLOOR),
        ExcludeClassCodesRule(class_codes=(99,)),
        PerDieLimitRule(limit=48),
        ClusterCountRule(count=48),
        RepeaterCountRule(count=48),
        RandomCountRule(count=48),
        PerClusterLimitRule(limit=48),
        PerRepeaterLimitRule(limit=48),
        PerWaferLimitRule(limit=48),
        RequireImageRule(),
        SizeRangeRule(size_field=SizeField.DIAMETER, minimum=5, maximum=18),
        IncludeClassCodesRule(class_codes=(1,)),
        LargeDefectPercentageRule(
            percentage=100,
            rounding=Rounding.FLOOR,
            size_field=SizeField.DIAMETER,
            minimum=5,
        ),
        LargeDefectCountRule(
            count=48,
            size_field=SizeField.DIAMETER,
            minimum=5,
        ),
        FinalClassDistributionRule(
            count=48,
            targets=(FinalClassTarget(value="Scratch", percentage=100),),
        ),
    )

    selected = sample_review(
        rows,
        program=ReviewSamplingProgram(rules=rules),
        identity_field="id",
        seed=31,
    )
    assert len(selected) == 48
    assert all(row["class_number"] == 1 for row in selected)
    assert all(row["images"] > 0 for row in selected)
    assert all(5 <= row["size_d"] <= 18 for row in selected)
