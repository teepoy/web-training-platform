from __future__ import annotations

import pytest

from sampling_rules import (
    Condition,
    ConditionalLimitRule,
    ConditionOperator,
    ConditionSet,
    DEFAULT_SAMPLING_SEED,
    ExtraFilterRule,
    GroupQuotaRule,
    GroupTarget,
    InsufficientPopulationError,
    InvalidSamplingRuleError,
    MatchMode,
    QuotaUnit,
    Rounding,
    SamplingProgram,
    ShortfallPolicy,
    TotalLimitRule,
    execute_sampling,
    sample,
)


def where(field: str, operator: ConditionOperator, value: object) -> ConditionSet:
    return ConditionSet(
        conditions=(Condition(field=field, operator=operator, value=value),),
        match=MatchMode.ALL,
    )


def make_rows() -> list[dict[str, object]]:
    return [
        {
            "id": index,
            "metadata": {
                "label": "a" if index < 8 else "b",
                "score": index / 10,
                "reviewed": index % 2 == 0,
            },
        }
        for index in range(12)
    ]


def test_total_limit_caps_the_final_random_draw() -> None:
    program = SamplingProgram(rules=(TotalLimitRule(limit=5),))

    result = execute_sampling(make_rows(), program=program, seed=17)

    assert len(result.rows) == 5
    assert result.plan.stages[0].rule_type == "total_limit"
    assert result.plan.stages[0].input_count == 12
    assert result.plan.stages[0].output_count == 5


def test_conditional_limit_only_caps_matching_rows() -> None:
    program = SamplingProgram(
        rules=(
            ConditionalLimitRule(
                where=where(
                    "metadata.label",
                    ConditionOperator.EQ,
                    "a",
                ),
                limit=3,
            ),
        )
    )

    selected = sample(make_rows(), program=program, seed=17)

    assert sum(row["metadata"]["label"] == "a" for row in selected) == 3
    assert sum(row["metadata"]["label"] == "b" for row in selected) == 4


def test_extra_filter_removes_ineligible_rows_before_sampling() -> None:
    program = SamplingProgram(
        rules=(
            ExtraFilterRule(
                where=where(
                    "metadata.score",
                    ConditionOperator.GTE,
                    0.6,
                )
            ),
            TotalLimitRule(limit=3),
        )
    )

    selected = sample(make_rows(), program=program, seed=17)

    assert len(selected) == 3
    assert all(row["metadata"]["score"] >= 0.6 for row in selected)


def test_group_count_quota_selects_explicit_totals() -> None:
    program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.COUNT,
                targets=(
                    GroupTarget(group=("a",), amount=2),
                    GroupTarget(group=("b",), amount=3),
                ),
                others_amount=0,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.ERROR,
            ),
        )
    )

    result = execute_sampling(make_rows(), program=program, seed=17)

    assert sum(row["metadata"]["label"] == "a" for row in result.rows) == 2
    assert sum(row["metadata"]["label"] == "b" for row in result.rows) == 3
    assert {quota.group: quota.quota for quota in result.plan.stages[0].quotas} == {
        ("a",): 2,
        ("b",): 3,
    }


def test_group_ratio_quota_uses_each_groups_own_population() -> None:
    program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.RATIO,
                targets=(
                    GroupTarget(group=("a",), amount=25),
                    GroupTarget(group=("b",), amount=75),
                ),
                others_amount=0,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.ERROR,
            ),
        )
    )

    selected = sample(make_rows(), program=program, seed=17)

    assert sum(row["metadata"]["label"] == "a" for row in selected) == 2
    assert sum(row["metadata"]["label"] == "b" for row in selected) == 3


def test_group_ratio_quota_uses_others_for_unlisted_groups() -> None:
    program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.RATIO,
                targets=(GroupTarget(group=("a",), amount=25),),
                others_amount=50,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.ERROR,
            ),
        )
    )

    selected = sample(make_rows(), program=program, seed=17)

    assert sum(row["metadata"]["label"] == "a" for row in selected) == 2
    assert sum(row["metadata"]["label"] == "b" for row in selected) == 2


def test_group_ratio_quota_rejects_percentages_over_100() -> None:
    program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.RATIO,
                targets=(GroupTarget(group=("a",), amount=101),),
                others_amount=0,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.ERROR,
            ),
        )
    )

    with pytest.raises(InvalidSamplingRuleError, match="between zero and 100"):
        sample(make_rows(), program=program, seed=17)


def test_group_ratio_two_percent_means_two_percent_of_group_population() -> None:
    rows = [{"id": index, "metadata": {"label": "a"}} for index in range(1_000)]
    program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.RATIO,
                targets=(GroupTarget(group=("a",), amount=2),),
                others_amount=0,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.ERROR,
            ),
        )
    )

    assert len(sample(rows, program=program)) == 20


def test_others_can_define_the_rule_for_every_group() -> None:
    program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.RATIO,
                targets=(),
                others_amount=50,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.ERROR,
            ),
        )
    )

    selected = sample(make_rows(), program=program)

    assert sum(row["metadata"]["label"] == "a" for row in selected) == 4
    assert sum(row["metadata"]["label"] == "b" for row in selected) == 2


def test_extra_filter_supports_nested_and_or_groups() -> None:
    program = SamplingProgram(
        rules=(
            ExtraFilterRule(
                where=ConditionSet(
                    match=MatchMode.ALL,
                    conditions=(
                        Condition(
                            field="metadata.reviewed",
                            operator=ConditionOperator.EQ,
                            value=True,
                        ),
                        ConditionSet(
                            match=MatchMode.ANY,
                            conditions=(
                                Condition(
                                    field="metadata.label",
                                    operator=ConditionOperator.EQ,
                                    value="a",
                                ),
                                Condition(
                                    field="metadata.score",
                                    operator=ConditionOperator.GTE,
                                    value=1.0,
                                ),
                            ),
                        ),
                    ),
                )
            ),
        )
    )

    selected = sample(make_rows(), program=program)

    assert [row["id"] for row in selected] == [0, 2, 4, 6, 10]


def test_group_shortfall_policy_is_explicit() -> None:
    strict_program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.COUNT,
                targets=(GroupTarget(group=("b",), amount=5),),
                others_amount=0,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.ERROR,
            ),
        )
    )
    permissive_program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.COUNT,
                targets=(GroupTarget(group=("b",), amount=5),),
                others_amount=0,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.TAKE_AVAILABLE,
            ),
        )
    )

    with pytest.raises(InsufficientPopulationError, match="requests 5"):
        sample(make_rows(), program=strict_program, seed=17)
    assert len(sample(make_rows(), program=permissive_program, seed=17)) == 4


def test_rule_order_is_fixed_and_reported() -> None:
    program = SamplingProgram(
        rules=(
            TotalLimitRule(limit=5),
            ExtraFilterRule(
                where=where(
                    "metadata.reviewed",
                    ConditionOperator.EQ,
                    True,
                )
            ),
        )
    )

    with pytest.raises(InvalidSamplingRuleError, match="rules must follow"):
        sample(make_rows(), program=program, seed=17)


def test_seeded_program_is_reproducible() -> None:
    program = SamplingProgram(
        rules=(
            ExtraFilterRule(
                where=where(
                    "metadata.score",
                    ConditionOperator.GTE,
                    0.2,
                )
            ),
            ConditionalLimitRule(
                where=where(
                    "metadata.label",
                    ConditionOperator.EQ,
                    "a",
                ),
                limit=4,
            ),
            TotalLimitRule(limit=6),
        )
    )

    first = sample(make_rows(), program=program, seed=23)
    second = sample(make_rows(), program=program, seed=23)

    assert first == second


def test_default_seed_is_fixed_at_42() -> None:
    program = SamplingProgram(rules=(TotalLimitRule(limit=5),))

    assert DEFAULT_SAMPLING_SEED == 42
    assert sample(make_rows(), program=program) == sample(
        make_rows(),
        program=program,
        seed=42,
    )
