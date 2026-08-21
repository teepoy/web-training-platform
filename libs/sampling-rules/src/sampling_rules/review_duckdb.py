from __future__ import annotations

import duckdb

from sampling_rules.duckdb_engine import (
    CompiledDuckDbSampling,
    DuckDbParameter,
    DuckDbSamplingExecution,
    DuckDbSamplingSource,
)
from sampling_rules.errors import InvalidSamplingRuleError
from sampling_rules.models import Rounding
from sampling_rules.review_sampling import (
    ClusterCountRule,
    ClusterPercentageRule,
    ExcludeClassCodesRule,
    FinalClassDistributionRule,
    IncludeClassCodesRule,
    LargeDefectCountRule,
    LargeDefectPercentageRule,
    PerClusterLimitRule,
    PerDieLimitRule,
    PerRepeaterLimitRule,
    PerWaferLimitRule,
    RandomCountRule,
    RandomPercentageRule,
    RepeaterCountRule,
    RepeaterPercentageRule,
    RequireImageRule,
    ReviewSamplingProgram,
    SizeRangeRule,
    _distribution_quotas,
    validate_review_sampling_program,
)


def _quote_identifier(value: str) -> str:
    if not value.strip() or "\x00" in value:
        raise InvalidSamplingRuleError("sampling identifiers cannot be empty")
    return '"' + value.replace('"', '""') + '"'


def _quote_path(value: str) -> str:
    return ".".join(_quote_identifier(part) for part in value.split("."))


def _rounding_expression(rounding: Rounding, population: str) -> str:
    raw = f"({population} * ? / 100.0)"
    if rounding is Rounding.FLOOR:
        return f"FLOOR({raw})"
    if rounding is Rounding.CEIL:
        return f"CEIL({raw})"
    return f"FLOOR({raw} + 0.5)"


def _filter_predicate(
    rule: ExcludeClassCodesRule
    | IncludeClassCodesRule
    | RequireImageRule
    | SizeRangeRule,
) -> tuple[str, list[DuckDbParameter]]:
    if isinstance(rule, ExcludeClassCodesRule):
        return '("class_number" IS NULL OR NOT ("class_number" = ANY(?)))', [
            list(rule.class_codes)
        ]
    if isinstance(rule, IncludeClassCodesRule):
        return '"class_number" = ANY(?)', [list(rule.class_codes)]
    if isinstance(rule, RequireImageRule):
        return '"images" > 0', []
    return (
        f"{_quote_identifier(rule.size_field.value)} BETWEEN ? AND ?",
        [rule.minimum, rule.maximum],
    )


def _selector_predicate(
    rule: ClusterPercentageRule
    | RepeaterPercentageRule
    | RandomPercentageRule
    | ClusterCountRule
    | RepeaterCountRule
    | RandomCountRule
    | LargeDefectPercentageRule
    | LargeDefectCountRule,
) -> tuple[str, list[DuckDbParameter]]:
    if isinstance(rule, ClusterPercentageRule | ClusterCountRule):
        return '"cluster_id" > 0', []
    if isinstance(rule, RepeaterPercentageRule | RepeaterCountRule):
        return '"repeater_id" > 0', []
    if isinstance(rule, LargeDefectPercentageRule | LargeDefectCountRule):
        return f"{_quote_identifier(rule.size_field.value)} >= ?", [rule.minimum]
    return "TRUE", []


def compile_duckdb_review_sampling(
    source: DuckDbSamplingSource,
    *,
    program: ReviewSamplingProgram,
    seed: int,
) -> CompiledDuckDbSampling:
    validate_review_sampling_program(program)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise InvalidSamplingRuleError(
            "review sampling seed must be a non-negative integer"
        )
    if not source.sql.strip():
        raise InvalidSamplingRuleError("DuckDB sampling source SQL cannot be empty")

    identity = _quote_path(source.identity_field)
    output = _quote_identifier(source.output_field)
    ctes = [f'"__review_source" AS ({source.sql})']
    parameters: list[DuckDbParameter] = list(source.parameters)

    filter_types = (
        ExcludeClassCodesRule,
        IncludeClassCodesRule,
        RequireImageRule,
        SizeRangeRule,
    )
    cap_types = (
        PerDieLimitRule,
        PerClusterLimitRule,
        PerRepeaterLimitRule,
        PerWaferLimitRule,
    )
    current = '"__review_source"'
    for index, rule in enumerate(program.rules):
        stage = f'"__review_step_{index}"'
        if isinstance(rule, filter_types):
            predicate, values = _filter_predicate(rule)
            ctes.append(f"{stage} AS (SELECT * FROM {current} WHERE {predicate})")
            parameters.extend(values)
            current = stage
            continue

        if isinstance(rule, FinalClassDistributionRule):
            target_stages: list[str] = []
            for target_index, (target, quota) in enumerate(
                zip(
                    rule.targets,
                    _distribution_quotas(rule),
                    strict=True,
                )
            ):
                ranked = f'"__review_step_{index}_target_{target_index}_ranked"'
                target_stage = f'"__review_step_{index}_target_{target_index}"'
                ctes.append(
                    f"{ranked} AS (SELECT *, ROW_NUMBER() OVER ("
                    f"ORDER BY HASH({identity}, ?, ?), {identity}) AS "
                    f'"__review_rank" FROM {current} '
                    f'WHERE "final_class" IS NOT DISTINCT FROM ?)'
                )
                parameters.extend(
                    [seed, f"FinalClassDistributionRule:{target.value!r}", target.value]
                )
                ctes.append(
                    f'{target_stage} AS (SELECT * EXCLUDE ("__review_rank") FROM {ranked} '
                    f'WHERE "__review_rank" <= ?)'
                )
                parameters.append(quota)
                target_stages.append(target_stage)
            ctes.append(
                f"{stage} AS ("
                + " UNION ALL ".join(
                    f"SELECT * FROM {target}" for target in target_stages
                )
                + ")"
            )
            current = stage
            continue

        if isinstance(rule, cap_types):
            if isinstance(rule, PerDieLimitRule):
                group_fields = ("inspection_time", "wafer_key", "index_x", "index_y")
                preserve = None
            elif isinstance(rule, PerClusterLimitRule):
                group_fields = ("cluster_id",)
                preserve = '"cluster_id" IS NULL OR "cluster_id" <= 0'
            elif isinstance(rule, PerRepeaterLimitRule):
                group_fields = ("repeater_id",)
                preserve = '"repeater_id" IS NULL OR "repeater_id" <= 0'
            else:
                group_fields = ("inspection_time", "wafer_key")
                preserve = None
            partition = ", ".join(_quote_identifier(field) for field in group_fields)
            ranked = f'"__review_step_{index}_ranked"'
            ctes.append(
                f"{ranked} AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY {partition} "
                f"ORDER BY HASH({identity}, ?, ?), {identity}) AS "
                f'"__review_cap_rank" FROM {current})'
            )
            parameters.extend([seed, type(rule).__name__])
            condition = '"__review_cap_rank" <= ?'
            if preserve is not None:
                condition = f"({preserve}) OR {condition}"
            ctes.append(
                f'{stage} AS (SELECT * EXCLUDE ("__review_cap_rank") FROM {ranked} '
                f"WHERE {condition})"
            )
            parameters.append(rule.limit)
            current = stage
            continue

        predicate, predicate_parameters = _selector_predicate(rule)
        ranked = f'"__review_step_{index}_ranked"'
        is_ratio = isinstance(
            rule,
            ClusterPercentageRule
            | RepeaterPercentageRule
            | RandomPercentageRule
            | LargeDefectPercentageRule,
        )
        population = ', COUNT(*) OVER () AS "__review_population"' if is_ratio else ""
        ctes.append(
            f"{ranked} AS (SELECT *, ROW_NUMBER() OVER ("
            f"ORDER BY HASH({identity}, ?, ?), {identity}) AS "
            f'"__review_rank"{population} FROM {current} WHERE {predicate})'
        )
        parameters.extend([seed, type(rule).__name__, *predicate_parameters])
        if is_ratio:
            quota = _rounding_expression(rule.rounding, '"__review_population"')
            parameters.append(rule.percentage)
            excluded = '"__review_rank", "__review_population"'
        else:
            quota = "?"
            parameters.append(rule.count)
            excluded = '"__review_rank"'
        ctes.append(
            f"{stage} AS (SELECT * EXCLUDE ({excluded}) FROM {ranked} "
            f'WHERE "__review_rank" <= {quota})'
        )
        current = stage

    sql = (
        f"WITH {', '.join(ctes)} SELECT {identity} AS {output} FROM {current} "
        f"ORDER BY HASH({identity}, ?, ?), {identity}"
    )
    parameters.extend([seed, "review-result"])
    return CompiledDuckDbSampling(sql=sql, parameters=tuple(parameters))


def execute_duckdb_review_sampling(
    connection: duckdb.DuckDBPyConnection,
    source: DuckDbSamplingSource,
    *,
    program: ReviewSamplingProgram,
    seed: int,
    batch_rows: int,
) -> DuckDbSamplingExecution:
    if (
        isinstance(batch_rows, bool)
        or not isinstance(batch_rows, int)
        or batch_rows <= 0
    ):
        raise InvalidSamplingRuleError("DuckDB sampling batch_rows must be positive")
    compiled = compile_duckdb_review_sampling(source, program=program, seed=seed)
    reader = connection.execute(
        compiled.sql, list(compiled.parameters)
    ).to_arrow_reader(batch_rows)
    return DuckDbSamplingExecution(reader=reader, compiled=compiled)
