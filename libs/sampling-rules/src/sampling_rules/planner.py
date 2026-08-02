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
    GroupSamplingRateRule,
    QuotaUnit,
    Rounding,
    ShortfallPolicy,
    TotalLimitRule,
    UnlistedGroupPolicy,
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


def _unlisted_quotas(
    populations: Mapping[GroupKey, int],
    configured: set[GroupKey],
    policy: UnlistedGroupPolicy,
) -> dict[GroupKey, int]:
    if policy is UnlistedGroupPolicy.KEEP:
        return {
            group: population
            for group, population in populations.items()
            if group not in configured
        }
    return {group: 0 for group in populations if group not in configured}


def _largest_remainder(
    ratios: Mapping[GroupKey, float],
    total: int,
) -> dict[GroupKey, int]:
    ideals = {group: total * ratio for group, ratio in ratios.items()}
    quotas = {group: math.floor(ideal) for group, ideal in ideals.items()}
    remaining = total - sum(quotas.values())
    ranked = sorted(
        ideals,
        key=lambda group: (
            -(ideals[group] - math.floor(ideals[group])),
            stable_group_key(group),
        ),
    )
    for group in ranked[:remaining]:
        quotas[group] += 1
    return quotas


def plan_group_quota(
    populations: Mapping[GroupKey, int],
    rule: GroupQuotaRule,
    *,
    total_limit: TotalLimitRule | None,
) -> tuple[GroupQuota, ...]:
    _validate_group_fields(rule.group_by)
    _validate_populations(populations)
    configured_targets = {target.group: target.amount for target in rule.targets}
    if not configured_targets:
        raise InvalidSamplingRuleError("group quota rules require at least one target")
    if len(configured_targets) != len(rule.targets):
        raise InvalidSamplingRuleError("group quota rules cannot repeat a group")
    configured = set(configured_targets)
    _validate_target_groups(populations, configured, rule.group_by)

    if rule.unit is QuotaUnit.COUNT:
        quotas: dict[GroupKey, int] = {}
        for group, amount in configured_targets.items():
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise InvalidSamplingRuleError(
                    "count targets must be non-negative integers"
                )
            quotas[group] = amount
    else:
        if total_limit is None:
            raise InvalidSamplingRuleError(
                "ratio-based group quotas require a later total limit rule"
            )
        if rule.unlisted is UnlistedGroupPolicy.KEEP:
            raise InvalidSamplingRuleError(
                "ratio-based group quotas cannot keep unlisted groups because "
                "the configured ratios define the complete final composition"
            )
        ratios: dict[GroupKey, float] = {}
        for group, amount in configured_targets.items():
            ratio = float(amount)
            if not math.isfinite(ratio) or ratio < 0 or ratio > 1:
                raise InvalidSamplingRuleError(
                    "ratio targets must be finite values between zero and one"
                )
            ratios[group] = ratio
        if not math.isclose(sum(ratios.values()), 1.0, abs_tol=1e-9):
            raise InvalidSamplingRuleError(
                "ratio-based group quotas must sum to exactly one"
            )
        quotas = _largest_remainder(ratios, total_limit.limit)

    quotas.update(_unlisted_quotas(populations, configured, rule.unlisted))
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


def plan_group_rates(
    populations: Mapping[GroupKey, int],
    rule: GroupSamplingRateRule,
) -> tuple[GroupQuota, ...]:
    _validate_group_fields(rule.group_by)
    _validate_populations(populations)
    configured_rates = {item.group: item.ratio for item in rule.rates}
    if not configured_rates:
        raise InvalidSamplingRuleError(
            "group sampling rate rules require at least one rate"
        )
    if len(configured_rates) != len(rule.rates):
        raise InvalidSamplingRuleError(
            "group sampling rate rules cannot repeat a group"
        )
    configured = set(configured_rates)
    _validate_target_groups(populations, configured, rule.group_by)

    quotas: dict[GroupKey, int] = {}
    for group, ratio in configured_rates.items():
        if not math.isfinite(ratio) or ratio < 0 or ratio > 1:
            raise InvalidSamplingRuleError(
                "group sampling rates must be finite values between zero and one"
            )
        quotas[group] = _rounded_count(populations[group] * ratio, rule.rounding)
    quotas.update(_unlisted_quotas(populations, configured, rule.unlisted))

    return tuple(
        GroupQuota(group=group, population=populations[group], quota=quotas[group])
        for group in sorted(populations, key=stable_group_key)
    )
