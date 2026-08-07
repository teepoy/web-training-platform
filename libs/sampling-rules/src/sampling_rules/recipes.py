from __future__ import annotations

import math
from collections.abc import Mapping

from sampling_rules.errors import InvalidSamplingRuleError
from sampling_rules.models import (
    Condition,
    ConditionOperator,
    ConditionSet,
    ExtraFilterRule,
    GroupQuotaRule,
    GroupTarget,
    MatchMode,
    QuotaUnit,
    Rounding,
    SamplingProgram,
    Scalar,
    ShortfallPolicy,
    TotalLimitRule,
)
from sampling_rules.spatial import (
    DYNAMIC_ADDER_FIELD,
    DYNAMIC_CLUSTER_FIELD,
    DYNAMIC_CLUSTER_ID_FIELD,
)


def _positive_count(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidSamplingRuleError(f"{label} must be a positive integer")
    return value


def _percentage(value: float, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidSamplingRuleError(f"{label} must be a number")
    percentage = float(value)
    if not math.isfinite(percentage) or percentage <= 0 or percentage > 100:
        raise InvalidSamplingRuleError(
            f"{label} must be a percentage greater than zero and at most 100"
        )
    return percentage


def _greater_than_zero(field: str) -> ConditionSet:
    return ConditionSet(
        conditions=(
            Condition(
                field=field,
                operator=ConditionOperator.GT,
                value=0,
            ),
        ),
        match=MatchMode.ALL,
    )


def clustered_count_program(count: int) -> SamplingProgram:
    """Sample at most ``count`` defects whose dynamic cluster ID is positive."""

    return SamplingProgram(
        rules=(
            ExtraFilterRule(where=_greater_than_zero(DYNAMIC_CLUSTER_ID_FIELD)),
            TotalLimitRule(limit=_positive_count(count, label="cluster sample count")),
        )
    )


def clustered_ratio_program(
    percentage: float,
    *,
    rounding: Rounding,
) -> SamplingProgram:
    """Sample a percentage of all dynamically clustered defects.

    The boolean ``dynamic_cluster`` group has target ``1`` for clustered rows;
    the Others branch is zero, so DBSCAN noise is excluded.
    """

    return SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=(DYNAMIC_CLUSTER_FIELD,),
                unit=QuotaUnit.RATIO,
                targets=(
                    GroupTarget(
                        group=(1,),
                        amount=_percentage(
                            percentage,
                            label="cluster sample ratio",
                        ),
                    ),
                ),
                others_amount=0,
                rounding=rounding,
                shortfall=ShortfallPolicy.TAKE_AVAILABLE,
            ),
        )
    )


def adder_count_program(count: int) -> SamplingProgram:
    """Sample at most ``count`` defects classified as dynamic adders."""

    return SamplingProgram(
        rules=(
            ExtraFilterRule(where=_greater_than_zero(DYNAMIC_ADDER_FIELD)),
            TotalLimitRule(limit=_positive_count(count, label="adder sample count")),
        )
    )


def per_die_cap_program(
    count: int,
    *,
    die_x_field: str,
    die_y_field: str,
) -> SamplingProgram:
    """Sample at most ``count`` defects independently from every die."""

    if not die_x_field.strip() or not die_y_field.strip():
        raise InvalidSamplingRuleError("per-die sampling requires both die fields")
    return SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=(die_x_field, die_y_field),
                unit=QuotaUnit.COUNT,
                targets=(),
                others_amount=_positive_count(count, label="per-die sample count"),
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.TAKE_AVAILABLE,
            ),
        )
    )


def clipped_log10_quota(
    population: int,
    *,
    minimum: int,
    maximum: int,
    rounding: Rounding,
) -> int:
    """Compute an integer ``clip(log10(population), minimum, maximum)`` quota."""

    if (
        isinstance(population, bool)
        or not isinstance(population, int)
        or population < 0
    ):
        raise InvalidSamplingRuleError(
            "prediction populations must be non-negative integers"
        )
    minimum = _positive_count(minimum, label="minimum prediction quota")
    maximum = _positive_count(maximum, label="maximum prediction quota")
    if minimum > maximum:
        raise InvalidSamplingRuleError(
            "minimum prediction quota cannot exceed maximum prediction quota"
        )
    if population == 0:
        return 0
    value = min(max(math.log10(population), minimum), maximum)
    if rounding is Rounding.FLOOR:
        return math.floor(value)
    if rounding is Rounding.CEIL:
        return math.ceil(value)
    return math.floor(value + 0.5)


def prediction_log_quota_program(
    populations: Mapping[Scalar, int],
    *,
    prediction_field: str,
    minimum: int,
    maximum: int,
    rounding: Rounding,
) -> SamplingProgram:
    """Build per-prediction count targets from clipped base-10 log populations."""

    if not prediction_field.strip():
        raise InvalidSamplingRuleError("prediction sampling requires a field")
    target_list: list[GroupTarget] = []
    for value, population in sorted(
        populations.items(),
        key=lambda item: f"{type(item[0]).__name__}:{item[0]!r}",
    ):
        quota = clipped_log10_quota(
            population,
            minimum=minimum,
            maximum=maximum,
            rounding=rounding,
        )
        if quota > 0:
            target_list.append(GroupTarget(group=(value,), amount=quota))
    targets = tuple(target_list)
    if not targets:
        raise InvalidSamplingRuleError(
            "prediction sampling requires at least one positive population"
        )
    return SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=(prediction_field,),
                unit=QuotaUnit.COUNT,
                targets=targets,
                others_amount=0,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.TAKE_AVAILABLE,
            ),
        )
    )
