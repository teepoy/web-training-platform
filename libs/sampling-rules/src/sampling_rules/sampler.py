from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import TypeVar, cast

from sampling_rules.errors import InvalidSamplingRuleError, MissingFieldError
from sampling_rules.models import (
    Condition,
    ConditionOperator,
    ConditionSet,
    ConditionalLimitRule,
    ExtraFilterRule,
    GroupKey,
    GroupQuotaRule,
    MatchMode,
    RuleStage,
    SamplingPlan,
    SamplingProgram,
    SamplingResult,
    Scalar,
)
from sampling_rules.planner import plan_group_quota
from sampling_rules.validation import validate_sampling_program

RowT = TypeVar("RowT", bound=Mapping[str, object])
DEFAULT_SAMPLING_SEED = 42


def _read_path(row: Mapping[str, object], path: str) -> Scalar:
    current: object = row
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise MissingFieldError(f"sampling field {path!r} is missing")
        current = current[part]
    if current is None or isinstance(current, str | int | float | bool):
        return current
    raise MissingFieldError(f"sampling field {path!r} must resolve to a scalar value")


def _sequence_value(condition: Condition) -> tuple[Scalar, ...]:
    if not isinstance(condition.value, tuple):
        raise InvalidSamplingRuleError(
            f"operator {condition.operator.value!r} requires a tuple value"
        )
    return condition.value


def _matches_condition(row: Mapping[str, object], condition: Condition) -> bool:
    actual = _read_path(row, condition.field)
    expected = condition.value
    operator = condition.operator
    if operator is ConditionOperator.EQ:
        return actual == expected
    if operator is ConditionOperator.NE:
        return actual != expected
    if operator is ConditionOperator.IN:
        return actual in _sequence_value(condition)
    if operator is ConditionOperator.NOT_IN:
        return actual not in _sequence_value(condition)
    if operator is ConditionOperator.BETWEEN:
        bounds = _sequence_value(condition)
        if len(bounds) != 2:
            raise InvalidSamplingRuleError(
                "between conditions require exactly two boundary values"
            )
        try:
            return bounds[0] <= actual <= bounds[1]  # type: ignore[operator]
        except TypeError as exc:
            raise InvalidSamplingRuleError(
                f"field {condition.field!r} cannot be compared to {bounds!r}"
            ) from exc
    try:
        if operator is ConditionOperator.GT:
            return actual > expected  # type: ignore[operator]
        if operator is ConditionOperator.GTE:
            return actual >= expected  # type: ignore[operator]
        if operator is ConditionOperator.LT:
            return actual < expected  # type: ignore[operator]
        if operator is ConditionOperator.LTE:
            return actual <= expected  # type: ignore[operator]
    except TypeError as exc:
        raise InvalidSamplingRuleError(
            f"field {condition.field!r} cannot be compared to {expected!r}"
        ) from exc
    raise InvalidSamplingRuleError(f"unsupported condition operator: {operator!r}")


def _matches(row: Mapping[str, object], where: ConditionSet) -> bool:
    if not where.conditions:
        raise InvalidSamplingRuleError("condition sets cannot be empty")
    matches = (
        _matches(row, condition)
        if isinstance(condition, ConditionSet)
        else _matches_condition(row, condition)
        for condition in where.conditions
    )
    return all(matches) if where.match is MatchMode.ALL else any(matches)


def _group_for(row: Mapping[str, object], group_by: tuple[str, ...]) -> GroupKey:
    return cast(GroupKey, tuple(_read_path(row, path) for path in group_by))


def _random_cap(rows: Sequence[RowT], limit: int, rng: random.Random) -> list[RowT]:
    if limit < 0:
        raise InvalidSamplingRuleError("limits cannot be negative")
    if len(rows) <= limit:
        return list(rows)
    return rng.sample(list(rows), limit)


def execute_sampling(
    rows: Sequence[RowT],
    *,
    program: SamplingProgram,
    seed: int = DEFAULT_SAMPLING_SEED,
) -> SamplingResult[RowT]:
    """Apply composable rules, then use seeded random draws for every reduction."""

    validate_sampling_program(program)
    rng = random.Random(seed)
    current = list(rows)
    stages: list[RuleStage] = []

    for rule in program.rules:
        before = len(current)
        quotas = ()
        if isinstance(rule, ExtraFilterRule):
            current = [row for row in current if _matches(row, rule.where)]
            rule_type = "extra_filter"
        elif isinstance(rule, ConditionalLimitRule):
            if rule.limit < 0:
                raise InvalidSamplingRuleError("conditional limits cannot be negative")
            matched: list[RowT] = []
            unmatched: list[RowT] = []
            for row in current:
                (matched if _matches(row, rule.where) else unmatched).append(row)
            current = unmatched + _random_cap(matched, rule.limit, rng)
            rng.shuffle(current)
            rule_type = "conditional_limit"
        elif isinstance(rule, GroupQuotaRule):
            grouped: dict[GroupKey, list[RowT]] = defaultdict(list)
            for row in current:
                grouped[_group_for(row, rule.group_by)].append(row)
            populations = {
                group: len(group_rows) for group, group_rows in grouped.items()
            }
            quotas = plan_group_quota(populations, rule)
            rule_type = "group_quota"
            current = []
            for quota in quotas:
                current.extend(rng.sample(grouped[quota.group], quota.quota))
            rng.shuffle(current)
        else:
            current = _random_cap(current, rule.limit, rng)
            rule_type = "total_limit"
        stages.append(
            RuleStage(
                rule_type=rule_type,
                input_count=before,
                output_count=len(current),
                quotas=quotas,
            )
        )

    return SamplingResult(
        rows=tuple(current),
        plan=SamplingPlan(
            input_count=len(rows),
            output_count=len(current),
            stages=tuple(stages),
        ),
    )


def sample(
    rows: Sequence[RowT],
    *,
    program: SamplingProgram,
    seed: int = DEFAULT_SAMPLING_SEED,
) -> list[RowT]:
    return list(execute_sampling(rows, program=program, seed=seed).rows)
