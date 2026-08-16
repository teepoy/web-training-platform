from __future__ import annotations

from sampling_rules.errors import InvalidSamplingRuleError
from sampling_rules.models import (
    ConditionalLimitRule,
    ExtraFilterRule,
    GroupQuotaRule,
    SamplingProgram,
    TotalLimitRule,
)


def validate_sampling_program(program: SamplingProgram) -> None:
    """Validate rule ordering and program-wide cardinality constraints."""

    rank = {
        ExtraFilterRule: 0,
        ConditionalLimitRule: 1,
        GroupQuotaRule: 2,
        TotalLimitRule: 3,
    }
    previous = -1
    group_rule_count = 0
    total_limit: TotalLimitRule | None = None
    for rule in program.rules:
        current = rank[type(rule)]
        if current < previous:
            raise InvalidSamplingRuleError(
                "rules must follow extra_filter -> conditional_limit -> "
                "group_selection -> total_limit order"
            )
        previous = current
        if isinstance(rule, GroupQuotaRule):
            group_rule_count += 1
        if isinstance(rule, TotalLimitRule):
            if total_limit is not None:
                raise InvalidSamplingRuleError(
                    "sampling programs allow only one total limit rule"
                )
            total_limit = rule
    if group_rule_count > 1:
        raise InvalidSamplingRuleError(
            "sampling programs allow only one group selection rule"
        )
    if total_limit is not None and total_limit.limit < 0:
        raise InvalidSamplingRuleError("total limits cannot be negative")
