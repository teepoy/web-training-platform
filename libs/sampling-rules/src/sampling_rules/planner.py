from __future__ import annotations

import math
from collections.abc import Mapping

from sampling_rules.errors import (
    InsufficientPopulationError,
    InvalidSamplingRuleError,
)
from sampling_rules.models import (
    GroupKey,
    GroupQuota,
    GroupQuotaRule,
    QuotaUnit,
    Rounding,
    ShortfallPolicy,
)


def stable_group_key(group: GroupKey) -> tuple[str, ...]:
    return tuple(f"{type(value).__name__}:{value!r}" for value in group)


def _validate_group_fields(group_by: tuple[str, ...]) -> None:
    if not group_by or any(not field.strip() for field in group_by):
        raise InvalidSamplingRuleError(
            "group rules require at least one non-empty group_by field"
        )


def _validate_populations(populations: Mapping[GroupKey, int]) -> None:
    invalid = {group: count for group, count in populations.items() if count < 0}
    if invalid:
        raise InvalidSamplingRuleError(
            f"group populations cannot be negative: {invalid!r}"
        )


def _validate_target_groups(
    populations: Mapping[GroupKey, int],
    configured: set[GroupKey],
    group_by: tuple[str, ...],
) -> None:
    invalid_width = [group for group in configured if len(group) != len(group_by)]
    if invalid_width:
        raise InvalidSamplingRuleError(
            "group target width must match group_by width: "
            f"{sorted(invalid_width, key=stable_group_key)!r}"
        )
    unknown = configured.difference(populations)
    if unknown:
        raise InvalidSamplingRuleError(
            f"group targets are absent from the population: "
            f"{sorted(unknown, key=stable_group_key)!r}"
        )


def plan_group_quota(
    populations: Mapping[GroupKey, int],
    rule: GroupQuotaRule,
) -> tuple[GroupQuota, ...]:
    _validate_group_fields(rule.group_by)
    _validate_populations(populations)
    configured_targets = {target.group: target.amount for target in rule.targets}
    if len(configured_targets) != len(rule.targets):
        raise InvalidSamplingRuleError("group quota rules cannot repeat a group")
    configured = set(configured_targets)
    _validate_target_groups(populations, configured, rule.group_by)

    all_amounts = (*configured_targets.values(), rule.others_amount)
    if rule.unit is QuotaUnit.COUNT:
        for amount in all_amounts:
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise InvalidSamplingRuleError(
                    "count targets must be non-negative integers"
                )
        quotas: dict[GroupKey, int] = {
            group: int(configured_targets.get(group, rule.others_amount))
            for group in populations
        }
    else:
        for amount in all_amounts:
            ratio = float(amount)
            if not math.isfinite(ratio) or ratio < 0 or ratio > 100:
                raise InvalidSamplingRuleError(
                    "sample ratio targets must be finite percentages between zero and 100"
                )
        quotas = {
            group: _rounded_count(
                populations[group]
                * float(configured_targets.get(group, rule.others_amount))
                / 100,
                rule.rounding,
            )
            for group in populations
        }
    for group, quota in tuple(quotas.items()):
        population = populations[group]
        if quota <= population:
            continue
        if rule.shortfall is ShortfallPolicy.ERROR:
            raise InsufficientPopulationError(
                f"group {group!r} requests {quota} samples from {population}"
            )
        quotas[group] = population

    return tuple(
        GroupQuota(group=group, population=populations[group], quota=quotas[group])
        for group in sorted(populations, key=stable_group_key)
    )


def _rounded_count(value: float, rounding: Rounding) -> int:
    if rounding is Rounding.FLOOR:
        return math.floor(value)
    if rounding is Rounding.CEIL:
        return math.ceil(value)
    return math.floor(value + 0.5)
