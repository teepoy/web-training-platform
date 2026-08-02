from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeAlias, TypeVar

Scalar: TypeAlias = str | int | float | bool | None
GroupKey: TypeAlias = tuple[Scalar, ...]


class ConditionOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    NOT_IN = "not_in"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"


class MatchMode(StrEnum):
    ALL = "all"
    ANY = "any"


class QuotaUnit(StrEnum):
    COUNT = "count"
    RATIO = "ratio"


class Rounding(StrEnum):
    FLOOR = "floor"
    CEIL = "ceil"
    NEAREST = "nearest"


class ShortfallPolicy(StrEnum):
    ERROR = "error"
    TAKE_AVAILABLE = "take_available"


class UnlistedGroupPolicy(StrEnum):
    EXCLUDE = "exclude"
    KEEP = "keep"


@dataclass(frozen=True, slots=True)
class Condition:
    field: str
    operator: ConditionOperator
    value: Scalar | tuple[Scalar, ...]


@dataclass(frozen=True, slots=True)
class ConditionSet:
    conditions: tuple[Condition, ...]
    match: MatchMode


@dataclass(frozen=True, slots=True)
class GlobalFilterRule:
    where: ConditionSet


@dataclass(frozen=True, slots=True)
class ConditionalLimitRule:
    where: ConditionSet
    limit: int


@dataclass(frozen=True, slots=True)
class GroupTarget:
    group: GroupKey
    amount: int | float


@dataclass(frozen=True, slots=True)
class GroupQuotaRule:
    group_by: tuple[str, ...]
    unit: QuotaUnit
    targets: tuple[GroupTarget, ...]
    shortfall: ShortfallPolicy
    unlisted: UnlistedGroupPolicy


@dataclass(frozen=True, slots=True)
class GroupRate:
    group: GroupKey
    ratio: float


@dataclass(frozen=True, slots=True)
class GroupSamplingRateRule:
    group_by: tuple[str, ...]
    rates: tuple[GroupRate, ...]
    rounding: Rounding
    unlisted: UnlistedGroupPolicy


@dataclass(frozen=True, slots=True)
class TotalLimitRule:
    limit: int


SamplingRule: TypeAlias = (
    GlobalFilterRule
    | ConditionalLimitRule
    | GroupQuotaRule
    | GroupSamplingRateRule
    | TotalLimitRule
)


@dataclass(frozen=True, slots=True)
class SamplingProgram:
    rules: tuple[SamplingRule, ...]


@dataclass(frozen=True, slots=True)
class GroupQuota:
    group: GroupKey
    population: int
    quota: int


@dataclass(frozen=True, slots=True)
class RuleStage:
    rule_type: str
    input_count: int
    output_count: int
    quotas: tuple[GroupQuota, ...] = ()


@dataclass(frozen=True, slots=True)
class SamplingPlan:
    input_count: int
    output_count: int
    stages: tuple[RuleStage, ...]


RowT = TypeVar("RowT")


@dataclass(frozen=True, slots=True)
class SamplingResult(Generic[RowT]):
    rows: tuple[RowT, ...]
    plan: SamplingPlan
