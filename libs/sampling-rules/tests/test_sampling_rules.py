from __future__ import annotations

import pytest

from sampling_rules import (
    Condition,
    ConditionalLimitRule,
    ConditionOperator,
    ConditionSet,
    GlobalFilterRule,
    GroupQuotaRule,
    GroupRate,
    GroupSamplingRateRule,
    GroupTarget,
    InsufficientPopulationError,
    InvalidSamplingRuleError,
    MatchMode,
    QuotaUnit,
    Rounding,
    SamplingProgram,
    ShortfallPolicy,
    TotalLimitRule,
    UnlistedGroupPolicy,
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


def test_global_filter_removes_ineligible_rows_before_sampling() -> None:
    program = SamplingProgram(
        rules=(
            GlobalFilterRule(
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
                shortfall=ShortfallPolicy.ERROR,
                unlisted=UnlistedGroupPolicy.EXCLUDE,
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


def test_group_ratio_quota_controls_final_composition() -> None:
    program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.RATIO,
                targets=(
                    GroupTarget(group=("a",), amount=0.6),
                    GroupTarget(group=("b",), amount=0.4),
                ),
                shortfall=ShortfallPolicy.ERROR,
                unlisted=UnlistedGroupPolicy.EXCLUDE,
            ),
            TotalLimitRule(limit=10),
        )
    )

    selected = sample(make_rows(), program=program, seed=17)

    assert len(selected) == 10
    assert sum(row["metadata"]["label"] == "a" for row in selected) == 6
    assert sum(row["metadata"]["label"] == "b" for row in selected) == 4


def test_group_ratio_quota_requires_total_limit() -> None:
    program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.RATIO,
                targets=(
                    GroupTarget(group=("a",), amount=0.5),
                    GroupTarget(group=("b",), amount=0.5),
                ),
                shortfall=ShortfallPolicy.ERROR,
                unlisted=UnlistedGroupPolicy.EXCLUDE,
            ),
        )
    )

    with pytest.raises(InvalidSamplingRuleError, match="total limit"):
        sample(make_rows(), program=program, seed=17)


def test_group_ratio_quota_rejects_unlisted_keep_policy() -> None:
    program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.RATIO,
                targets=(GroupTarget(group=("a",), amount=1.0),),
                shortfall=ShortfallPolicy.ERROR,
                unlisted=UnlistedGroupPolicy.KEEP,
            ),
            TotalLimitRule(limit=4),
        )
    )

    with pytest.raises(InvalidSamplingRuleError, match="complete final composition"):
        sample(make_rows(), program=program, seed=17)


def test_group_sampling_rate_uses_each_groups_own_population() -> None:
    program = SamplingProgram(
        rules=(
            GroupSamplingRateRule(
                group_by=("metadata.label",),
                rates=(
                    GroupRate(group=("a",), ratio=0.25),
                    GroupRate(group=("b",), ratio=0.75),
                ),
                rounding=Rounding.NEAREST,
                unlisted=UnlistedGroupPolicy.EXCLUDE,
            ),
        )
    )

    selected = sample(make_rows(), program=program, seed=17)

    assert sum(row["metadata"]["label"] == "a" for row in selected) == 2
    assert sum(row["metadata"]["label"] == "b" for row in selected) == 3


def test_group_shortfall_policy_is_explicit() -> None:
    strict_program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.COUNT,
                targets=(GroupTarget(group=("b",), amount=5),),
                shortfall=ShortfallPolicy.ERROR,
                unlisted=UnlistedGroupPolicy.EXCLUDE,
            ),
        )
    )
    permissive_program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("metadata.label",),
                unit=QuotaUnit.COUNT,
                targets=(GroupTarget(group=("b",), amount=5),),
                shortfall=ShortfallPolicy.TAKE_AVAILABLE,
                unlisted=UnlistedGroupPolicy.EXCLUDE,
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
            GlobalFilterRule(
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
            GlobalFilterRule(
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
