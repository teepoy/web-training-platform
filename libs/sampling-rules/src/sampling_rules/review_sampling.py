from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias, TypeVar

from sampling_rules.errors import InvalidSamplingRuleError, MissingFieldError
from sampling_rules.models import Rounding

ReviewRowT = TypeVar("ReviewRowT", bound=Mapping[str, object])


@dataclass(frozen=True, slots=True)
class ClusterPercentageRule:
    percentage: float
    rounding: Rounding


@dataclass(frozen=True, slots=True)
class RepeaterPercentageRule:
    percentage: float
    rounding: Rounding


@dataclass(frozen=True, slots=True)
class RandomPercentageRule:
    percentage: float
    rounding: Rounding


@dataclass(frozen=True, slots=True)
class ExcludeClassCodesRule:
    class_codes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RequireImageRule:
    pass


@dataclass(frozen=True, slots=True)
class SizeRangeRule:
    size_field: SizeField
    minimum: float
    maximum: float


@dataclass(frozen=True, slots=True)
class IncludeClassCodesRule:
    class_codes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PerDieLimitRule:
    limit: int


@dataclass(frozen=True, slots=True)
class PerClusterLimitRule:
    limit: int


@dataclass(frozen=True, slots=True)
class PerRepeaterLimitRule:
    limit: int


@dataclass(frozen=True, slots=True)
class PerWaferLimitRule:
    limit: int


@dataclass(frozen=True, slots=True)
class FinalClassTarget:
    value: str | None
    percentage: float


@dataclass(frozen=True, slots=True)
class FinalClassDistributionRule:
    count: int
    targets: tuple[FinalClassTarget, ...]


@dataclass(frozen=True, slots=True)
class ClusterCountRule:
    count: int


@dataclass(frozen=True, slots=True)
class RepeaterCountRule:
    count: int


@dataclass(frozen=True, slots=True)
class RandomCountRule:
    count: int


class SizeField(StrEnum):
    WIDTH = "size_x"
    HEIGHT = "size_y"
    DIAMETER = "size_d"
    AREA = "area"


@dataclass(frozen=True, slots=True)
class LargeDefectPercentageRule:
    percentage: float
    rounding: Rounding
    size_field: SizeField
    minimum: float


@dataclass(frozen=True, slots=True)
class LargeDefectCountRule:
    count: int
    size_field: SizeField
    minimum: float


ReviewSamplingRule: TypeAlias = (
    ClusterPercentageRule
    | RepeaterPercentageRule
    | RandomPercentageRule
    | ExcludeClassCodesRule
    | RequireImageRule
    | SizeRangeRule
    | IncludeClassCodesRule
    | PerDieLimitRule
    | PerClusterLimitRule
    | PerRepeaterLimitRule
    | PerWaferLimitRule
    | FinalClassDistributionRule
    | ClusterCountRule
    | RepeaterCountRule
    | RandomCountRule
    | LargeDefectPercentageRule
    | LargeDefectCountRule
)


class ReviewSamplingPhase(StrEnum):
    ELIGIBILITY = "eligibility"
    SELECTOR = "selector"
    CAP = "cap"


@dataclass(frozen=True, slots=True)
class ReviewSamplingRuleDescriptor:
    id: str
    phase: ReviewSamplingPhase
    rule_type: type[ReviewSamplingRule]


REVIEW_SAMPLING_RULE_CATALOG = (
    ReviewSamplingRuleDescriptor(
        "cluster_percentage", ReviewSamplingPhase.SELECTOR, ClusterPercentageRule
    ),
    ReviewSamplingRuleDescriptor(
        "repeater_percentage", ReviewSamplingPhase.SELECTOR, RepeaterPercentageRule
    ),
    ReviewSamplingRuleDescriptor(
        "random_percentage", ReviewSamplingPhase.SELECTOR, RandomPercentageRule
    ),
    ReviewSamplingRuleDescriptor(
        "exclude_class_codes", ReviewSamplingPhase.ELIGIBILITY, ExcludeClassCodesRule
    ),
    ReviewSamplingRuleDescriptor(
        "per_die_limit", ReviewSamplingPhase.CAP, PerDieLimitRule
    ),
    ReviewSamplingRuleDescriptor(
        "cluster_count", ReviewSamplingPhase.SELECTOR, ClusterCountRule
    ),
    ReviewSamplingRuleDescriptor(
        "repeater_count", ReviewSamplingPhase.SELECTOR, RepeaterCountRule
    ),
    ReviewSamplingRuleDescriptor(
        "random_count", ReviewSamplingPhase.SELECTOR, RandomCountRule
    ),
    ReviewSamplingRuleDescriptor(
        "per_cluster_limit", ReviewSamplingPhase.CAP, PerClusterLimitRule
    ),
    ReviewSamplingRuleDescriptor(
        "per_repeater_limit", ReviewSamplingPhase.CAP, PerRepeaterLimitRule
    ),
    ReviewSamplingRuleDescriptor(
        "per_wafer_limit", ReviewSamplingPhase.CAP, PerWaferLimitRule
    ),
    ReviewSamplingRuleDescriptor(
        "require_image", ReviewSamplingPhase.ELIGIBILITY, RequireImageRule
    ),
    ReviewSamplingRuleDescriptor(
        "size_range", ReviewSamplingPhase.ELIGIBILITY, SizeRangeRule
    ),
    ReviewSamplingRuleDescriptor(
        "include_class_codes", ReviewSamplingPhase.ELIGIBILITY, IncludeClassCodesRule
    ),
    ReviewSamplingRuleDescriptor(
        "large_defect_percentage",
        ReviewSamplingPhase.SELECTOR,
        LargeDefectPercentageRule,
    ),
    ReviewSamplingRuleDescriptor(
        "large_defect_count", ReviewSamplingPhase.SELECTOR, LargeDefectCountRule
    ),
    ReviewSamplingRuleDescriptor(
        "final_class_distribution",
        ReviewSamplingPhase.SELECTOR,
        FinalClassDistributionRule,
    ),
)


@dataclass(frozen=True, slots=True)
class ReviewSamplingProgram:
    rules: tuple[ReviewSamplingRule, ...]


def validate_review_sampling_program(program: ReviewSamplingProgram) -> None:
    descriptors = {
        descriptor.rule_type: descriptor for descriptor in REVIEW_SAMPLING_RULE_CATALOG
    }
    observed: set[type[object]] = set()
    has_reducer = False
    for rule in program.rules:
        descriptor = descriptors.get(type(rule))
        if descriptor is None:
            raise InvalidSamplingRuleError(
                f"unsupported review sampling rule: {type(rule)!r}"
            )
        if type(rule) in observed:
            raise InvalidSamplingRuleError(
                f"review sampling rule {descriptor.id!r} cannot be enabled more than once"
            )
        observed.add(type(rule))
        has_reducer = (
            has_reducer or descriptor.phase is not ReviewSamplingPhase.ELIGIBILITY
        )

        if isinstance(
            rule,
            ClusterPercentageRule
            | RepeaterPercentageRule
            | RandomPercentageRule
            | LargeDefectPercentageRule,
        ):
            _rounded_quota(1, rule.percentage, rule.rounding)
        if isinstance(
            rule,
            ClusterCountRule
            | RepeaterCountRule
            | RandomCountRule
            | LargeDefectCountRule,
        ):
            _positive_count(rule.count)
        if isinstance(
            rule,
            PerDieLimitRule
            | PerClusterLimitRule
            | PerRepeaterLimitRule
            | PerWaferLimitRule,
        ):
            _positive_count(rule.limit)
        if isinstance(rule, ExcludeClassCodesRule | IncludeClassCodesRule):
            _class_codes(rule.class_codes)
        if isinstance(rule, SizeRangeRule):
            minimum = float(rule.minimum)
            maximum = float(rule.maximum)
            if (
                not math.isfinite(minimum)
                or not math.isfinite(maximum)
                or minimum < 0
                or maximum < minimum
            ):
                raise InvalidSamplingRuleError(
                    "size range requires finite non-negative bounds with minimum <= maximum"
                )
        if isinstance(rule, LargeDefectPercentageRule | LargeDefectCountRule):
            minimum = float(rule.minimum)
            if not math.isfinite(minimum) or minimum < 0:
                raise InvalidSamplingRuleError(
                    "large-defect minimum must be a finite non-negative number"
                )
        if isinstance(rule, FinalClassDistributionRule):
            _distribution_quotas(rule)

    if not program.rules:
        raise InvalidSamplingRuleError("review sampling requires at least one rule")
    if not has_reducer:
        raise InvalidSamplingRuleError(
            "review sampling requires at least one selector or cap rule"
        )


def _scalar(row: Mapping[str, object], field: str) -> str | int | float | bool | None:
    if field not in row:
        raise MissingFieldError(f"review sampling field {field!r} is missing")
    value = row[field]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise MissingFieldError(f"review sampling field {field!r} must be scalar")


def _positive_id(row: Mapping[str, object], field: str) -> bool:
    value = _scalar(row, field)
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def _rounded_quota(population: int, percentage: float, rounding: Rounding) -> int:
    if isinstance(percentage, bool) or not isinstance(percentage, int | float):
        raise InvalidSamplingRuleError("sampling percentage must be a number")
    value = float(percentage)
    if not math.isfinite(value) or value <= 0 or value > 100:
        raise InvalidSamplingRuleError(
            "sampling percentage must be greater than zero and at most 100"
        )
    raw = population * value / 100
    if rounding is Rounding.FLOOR:
        return math.floor(raw)
    if rounding is Rounding.CEIL:
        return math.ceil(raw)
    return math.floor(raw + 0.5)


def _positive_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidSamplingRuleError("sampling count must be a positive integer")
    return value


def _at_least(
    row: Mapping[str, object],
    *,
    field: SizeField,
    minimum: float,
) -> bool:
    if isinstance(minimum, bool) or not isinstance(minimum, int | float):
        raise InvalidSamplingRuleError("large-defect minimum must be a number")
    minimum_value = float(minimum)
    if not math.isfinite(minimum_value) or minimum_value < 0:
        raise InvalidSamplingRuleError(
            "large-defect minimum must be a finite non-negative number"
        )
    value = _scalar(row, field.value)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MissingFieldError(
            f"review sampling field {field.value!r} must be numeric"
        )
    return float(value) >= minimum_value


def _numeric(row: Mapping[str, object], field: str) -> float:
    value = _scalar(row, field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MissingFieldError(f"review sampling field {field!r} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise InvalidSamplingRuleError(
            f"review sampling field {field!r} must be finite"
        )
    return result


def _class_codes(values: tuple[int, ...]) -> frozenset[int]:
    if not values or any(
        isinstance(value, bool) or not isinstance(value, int) for value in values
    ):
        raise InvalidSamplingRuleError(
            "class-code rules require at least one integer class code"
        )
    if len(values) != len(set(values)):
        raise InvalidSamplingRuleError("class-code rules cannot contain duplicates")
    return frozenset(values)


def _eligible(
    row: Mapping[str, object],
    rule: ExcludeClassCodesRule
    | RequireImageRule
    | SizeRangeRule
    | IncludeClassCodesRule,
) -> bool:
    if isinstance(rule, ExcludeClassCodesRule):
        return _scalar(row, "class_number") not in _class_codes(rule.class_codes)
    if isinstance(rule, IncludeClassCodesRule):
        return _scalar(row, "class_number") in _class_codes(rule.class_codes)
    if isinstance(rule, RequireImageRule):
        return _numeric(row, "images") > 0
    minimum = float(rule.minimum)
    maximum = float(rule.maximum)
    if (
        not math.isfinite(minimum)
        or not math.isfinite(maximum)
        or minimum < 0
        or maximum < minimum
    ):
        raise InvalidSamplingRuleError(
            "size range requires finite non-negative bounds with minimum <= maximum"
        )
    return minimum <= _numeric(row, rule.size_field.value) <= maximum


def _priority(*, seed: int, namespace: str, identity: object) -> bytes:
    payload = f"{seed}\0{namespace}\0{type(identity).__name__}:{identity!r}".encode()
    return hashlib.blake2b(payload, digest_size=16).digest()


def _cap_groups(
    rows: Sequence[ReviewRowT],
    *,
    rule: PerDieLimitRule
    | PerClusterLimitRule
    | PerRepeaterLimitRule
    | PerWaferLimitRule,
    identity_field: str,
    seed: int,
) -> list[ReviewRowT]:
    limit = _positive_count(rule.limit)
    groups: dict[tuple[object, ...], list[ReviewRowT]] = defaultdict(list)
    unmatched: list[ReviewRowT] = []
    for row in rows:
        if isinstance(rule, PerDieLimitRule):
            key = (
                _scalar(row, "inspection_time"),
                _scalar(row, "wafer_key"),
                _scalar(row, "index_x"),
                _scalar(row, "index_y"),
            )
        elif isinstance(rule, PerWaferLimitRule):
            key = (
                _scalar(row, "inspection_time"),
                _scalar(row, "wafer_key"),
            )
        elif isinstance(rule, PerClusterLimitRule):
            if not _positive_id(row, "cluster_id"):
                unmatched.append(row)
                continue
            key = (_scalar(row, "cluster_id"),)
        else:
            if not _positive_id(row, "repeater_id"):
                unmatched.append(row)
                continue
            key = (_scalar(row, "repeater_id"),)
        groups[key].append(row)

    result = list(unmatched)
    namespace = type(rule).__name__
    for key in sorted(groups, key=repr):
        result.extend(
            sorted(
                groups[key],
                key=lambda row: _priority(
                    seed=seed,
                    namespace=namespace,
                    identity=_scalar(row, identity_field),
                ),
            )[:limit]
        )
    return result


def _distribution_quotas(rule: FinalClassDistributionRule) -> tuple[int, ...]:
    count = _positive_count(rule.count)
    if not rule.targets:
        raise InvalidSamplingRuleError(
            "final-class distribution requires at least one target"
        )
    values = [target.value for target in rule.targets]
    if len(values) != len(set(values)):
        raise InvalidSamplingRuleError(
            "final-class distribution targets cannot contain duplicate values"
        )
    percentages = [float(target.percentage) for target in rule.targets]
    if any(
        isinstance(target.percentage, bool)
        or not isinstance(target.percentage, int | float)
        or not math.isfinite(percentage)
        or percentage <= 0
        or percentage > 100
        for target, percentage in zip(rule.targets, percentages, strict=True)
    ):
        raise InvalidSamplingRuleError(
            "final-class distribution percentages must be greater than zero and at most 100"
        )
    if not math.isclose(sum(percentages), 100.0, rel_tol=0, abs_tol=1e-6):
        raise InvalidSamplingRuleError(
            "final-class distribution percentages must total exactly 100"
        )

    raw = [count * percentage / 100 for percentage in percentages]
    quotas = [math.floor(value) for value in raw]
    remaining = count - sum(quotas)
    order = sorted(
        range(len(raw)),
        key=lambda index: (-(raw[index] - quotas[index]), repr(values[index])),
    )
    for index in order[:remaining]:
        quotas[index] += 1
    return tuple(quotas)


def sample_review(
    rows: Sequence[ReviewRowT],
    *,
    program: ReviewSamplingProgram,
    identity_field: str,
    seed: int,
) -> list[ReviewRowT]:
    validate_review_sampling_program(program)
    if not identity_field.strip():
        raise InvalidSamplingRuleError("review sampling identity field is required")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise InvalidSamplingRuleError(
            "review sampling seed must be a non-negative integer"
        )
    identities: dict[object, ReviewRowT] = {}
    for row in rows:
        identity = _scalar(row, identity_field)
        if identity is None:
            raise InvalidSamplingRuleError("review sampling identities cannot be null")
        if identity in identities:
            raise InvalidSamplingRuleError(
                f"review sampling identity {identity!r} is duplicated"
            )
        identities[identity] = row

    filter_types = (
        ExcludeClassCodesRule,
        RequireImageRule,
        SizeRangeRule,
        IncludeClassCodesRule,
    )
    eligible = list(rows)
    for rule in program.rules:
        if isinstance(rule, filter_types):
            eligible = [row for row in eligible if _eligible(row, rule)]

    cap_types = (
        PerDieLimitRule,
        PerClusterLimitRule,
        PerRepeaterLimitRule,
        PerWaferLimitRule,
    )
    selector_rules = [
        rule
        for rule in program.rules
        if not isinstance(rule, filter_types) and not isinstance(rule, cap_types)
    ]
    selected: dict[object, ReviewRowT] = {}
    for rule in selector_rules:
        namespace = type(rule).__name__
        if isinstance(rule, FinalClassDistributionRule):
            for target, quota in zip(
                rule.targets,
                _distribution_quotas(rule),
                strict=True,
            ):
                candidates = [
                    row
                    for row in eligible
                    if _scalar(row, "final_class") == target.value
                ]
                chosen = sorted(
                    candidates,
                    key=lambda row: _priority(
                        seed=seed,
                        namespace=f"{namespace}:{target.value!r}",
                        identity=_scalar(row, identity_field),
                    ),
                )[:quota]
                for row in chosen:
                    selected[_scalar(row, identity_field)] = row
            continue
        if isinstance(rule, ClusterPercentageRule | ClusterCountRule):
            candidates = [row for row in eligible if _positive_id(row, "cluster_id")]
        elif isinstance(rule, RepeaterPercentageRule | RepeaterCountRule):
            candidates = [row for row in eligible if _positive_id(row, "repeater_id")]
        elif isinstance(rule, LargeDefectPercentageRule | LargeDefectCountRule):
            candidates = [
                row
                for row in eligible
                if _at_least(
                    row,
                    field=rule.size_field,
                    minimum=rule.minimum,
                )
            ]
        else:
            candidates = list(eligible)

        if isinstance(
            rule,
            ClusterPercentageRule
            | RepeaterPercentageRule
            | RandomPercentageRule
            | LargeDefectPercentageRule,
        ):
            quota = _rounded_quota(
                len(candidates),
                rule.percentage,
                rule.rounding,
            )
        else:
            quota = min(len(candidates), _positive_count(rule.count))

        chosen = sorted(
            candidates,
            key=lambda row: _priority(
                seed=seed,
                namespace=namespace,
                identity=_scalar(row, identity_field),
            ),
        )[:quota]
        for row in chosen:
            selected[_scalar(row, identity_field)] = row

    current = list(selected.values()) if selector_rules else eligible
    cap_rank = {
        PerDieLimitRule: 0,
        PerClusterLimitRule: 1,
        PerRepeaterLimitRule: 2,
        PerWaferLimitRule: 3,
    }
    cap_rules = sorted(
        (rule for rule in program.rules if isinstance(rule, cap_types)),
        key=lambda rule: cap_rank[type(rule)],
    )
    for rule in cap_rules:
        current = _cap_groups(
            current,
            rule=rule,
            identity_field=identity_field,
            seed=seed,
        )

    return sorted(
        current,
        key=lambda row: _priority(
            seed=seed,
            namespace="review-result",
            identity=_scalar(row, identity_field),
        ),
    )
