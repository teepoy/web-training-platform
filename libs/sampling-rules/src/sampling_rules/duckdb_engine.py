from __future__ import annotations

import math
from dataclasses import dataclass

import duckdb
import pyarrow as pa

from sampling_rules.errors import InvalidSamplingRuleError
from sampling_rules.models import (
    Condition,
    ConditionOperator,
    ConditionSet,
    ConditionalLimitRule,
    ExtraFilterRule,
    GroupQuotaRule,
    MatchMode,
    QuotaUnit,
    Rounding,
    SamplingProgram,
    ShortfallPolicy,
    TotalLimitRule,
)
from sampling_rules.spatial import (
    DYNAMIC_ADDER_DISTANCE_FIELD,
    DYNAMIC_ADDER_FIELD,
    DYNAMIC_ADDER_REFERENCE_INDEX_FIELD,
    DYNAMIC_CLUSTER_FIELD,
    DYNAMIC_CLUSTER_ID_FIELD,
    DYNAMIC_CLUSTER_NEIGHBOR_COUNT_FIELD,
    DYNAMIC_CLUSTER_ROLE_FIELD,
    AdderMatchMode,
    DynamicAdderConfig,
    DynamicClusterConfig,
    validate_dynamic_adder_config,
    validate_dynamic_cluster_config,
)
from sampling_rules.validation import validate_sampling_program

DuckDbParameter = (
    bool | int | float | str | None | list[bool] | list[int] | list[float] | list[str]
)


@dataclass(frozen=True, slots=True)
class DuckDbSamplingSource:
    """A trusted relational input for the DuckDB sampling compiler.

    The SQL must be validated by the caller when it crosses a trust boundary.
    It may select from a DuckDB table/view or from an explicitly registered
    Arrow Table, Dataset, Scanner, RecordBatchReader, or dataframe.
    """

    sql: str
    parameters: tuple[DuckDbParameter, ...]
    identity_field: str
    output_field: str

    @classmethod
    def relation(
        cls,
        relation: str,
        *,
        identity_field: str,
        output_field: str,
    ) -> DuckDbSamplingSource:
        return cls(
            sql=f"SELECT * FROM {_quote_identifier(relation)}",
            parameters=(),
            identity_field=identity_field,
            output_field=output_field,
        )


@dataclass(frozen=True, slots=True)
class CompiledDuckDbSampling:
    sql: str
    parameters: tuple[DuckDbParameter, ...]


@dataclass(frozen=True, slots=True)
class DuckDbSamplingExecution:
    reader: pa.RecordBatchReader
    compiled: CompiledDuckDbSampling


def enrich_duckdb_sampling_source(
    source: DuckDbSamplingSource,
    *,
    adder_config: DynamicAdderConfig | None = None,
    reference_source: DuckDbSamplingSource | None = None,
    cluster_config: DynamicClusterConfig | None = None,
) -> DuckDbSamplingSource:
    """Add dynamic spatial fields to a relational sampling source.

    Coordinate matching uses radius-sized grid cells to restrict candidate
    joins. Cluster connected components use DuckDB's keyed recursive CTE, so
    the component state stays one row per core point rather than accumulating
    every traversal path.
    """

    if adder_config is None and cluster_config is None:
        raise InvalidSamplingRuleError(
            "DuckDB spatial enrichment requires an adder or cluster config"
        )
    if not source.sql.strip():
        raise InvalidSamplingRuleError("DuckDB sampling source SQL cannot be empty")
    if adder_config is not None and reference_source is None:
        raise InvalidSamplingRuleError(
            "dynamic adder calculation requires a user-selected reference layer"
        )

    row_index = '"__sampling_spatial_row_index"'
    ctes = [f'"__sampling_spatial_raw" AS ({source.sql})']
    parameters: list[DuckDbParameter] = list(source.parameters)
    identity = _quote_path(source.identity_field)
    ctes.append(
        f'"__sampling_spatial_base" AS (SELECT *, '
        f"ROW_NUMBER() OVER (ORDER BY {identity}) - 1 AS {row_index} "
        f'FROM "__sampling_spatial_raw")'
    )
    feature_joins: list[str] = []
    feature_columns: list[str] = []

    if adder_config is not None:
        assert reference_source is not None
        adder_ctes, adder_parameters = _compile_dynamic_adder_ctes(
            reference_source,
            config=adder_config,
        )
        ctes.extend(adder_ctes)
        parameters.extend(adder_parameters)
        feature_joins.append(
            f'LEFT JOIN "__sampling_adder_features" AS adder '
            f"ON adder.{row_index} = base.{row_index}"
        )
        feature_columns.extend(
            [
                f"adder.{_quote_identifier(DYNAMIC_ADDER_FIELD)}",
                f"adder.{_quote_identifier(DYNAMIC_ADDER_DISTANCE_FIELD)}",
                f"adder.{_quote_identifier(DYNAMIC_ADDER_REFERENCE_INDEX_FIELD)}",
            ]
        )

    if cluster_config is not None:
        cluster_ctes, cluster_parameters = _compile_dynamic_cluster_ctes(
            config=cluster_config
        )
        ctes.extend(cluster_ctes)
        parameters.extend(cluster_parameters)
        feature_joins.append(
            f'LEFT JOIN "__sampling_cluster_features" AS cluster '
            f"ON cluster.{row_index} = base.{row_index}"
        )
        feature_columns.extend(
            [
                f"cluster.{_quote_identifier(DYNAMIC_CLUSTER_FIELD)}",
                f"cluster.{_quote_identifier(DYNAMIC_CLUSTER_ID_FIELD)}",
                f"cluster.{_quote_identifier(DYNAMIC_CLUSTER_NEIGHBOR_COUNT_FIELD)}",
                f"cluster.{_quote_identifier(DYNAMIC_CLUSTER_ROLE_FIELD)}",
            ]
        )

    sql = (
        f"WITH RECURSIVE {', '.join(ctes)} "
        f"SELECT base.* EXCLUDE ({row_index}), {', '.join(feature_columns)} "
        f'FROM "__sampling_spatial_base" AS base {" ".join(feature_joins)}'
    )
    return DuckDbSamplingSource(
        sql=sql,
        parameters=tuple(parameters),
        identity_field=source.identity_field,
        output_field=source.output_field,
    )


def compile_duckdb_sampling(
    source: DuckDbSamplingSource,
    *,
    program: SamplingProgram,
    seed: int,
) -> CompiledDuckDbSampling:
    """Compile a sampling program into one parameterized DuckDB query."""

    validate_sampling_program(program)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise InvalidSamplingRuleError("sampling seed must be a non-negative integer")
    if not source.sql.strip():
        raise InvalidSamplingRuleError("DuckDB sampling source SQL cannot be empty")

    identity = _quote_path(source.identity_field)
    output = _quote_identifier(source.output_field)
    ctes = [f'"__sampling_source" AS ({source.sql})']
    parameters: list[DuckDbParameter] = list(source.parameters)
    current = '"__sampling_source"'
    conditional_index = 0
    extra_index = 0

    for rule in program.rules:
        if isinstance(rule, ExtraFilterRule):
            predicate, predicate_parameters = _compile_condition_set(rule.where)
            stage = f'"__sampling_extra_{extra_index}"'
            ctes.append(f"{stage} AS (SELECT * FROM {current} WHERE {predicate})")
            parameters.extend(predicate_parameters)
            current = stage
            extra_index += 1
            continue

        if isinstance(rule, ConditionalLimitRule):
            if rule.limit < 0:
                raise InvalidSamplingRuleError("conditional limits cannot be negative")
            predicate, predicate_parameters = _compile_condition_set(rule.where)
            match_column = _quote_identifier(
                f"__sampling_conditional_match_{conditional_index}"
            )
            rank_column = _quote_identifier(
                f"__sampling_conditional_rank_{conditional_index}"
            )
            marked = f'"__sampling_conditional_marked_{conditional_index}"'
            ranked = f'"__sampling_conditional_ranked_{conditional_index}"'
            stage = f'"__sampling_conditional_{conditional_index}"'
            ctes.append(
                f"{marked} AS (SELECT *, {predicate} AS {match_column} FROM {current})"
            )
            parameters.extend(predicate_parameters)
            ctes.append(
                f"{ranked} AS (SELECT *, ROW_NUMBER() OVER ("
                f"PARTITION BY {match_column} ORDER BY HASH({identity}, ?), {identity}"
                f") AS {rank_column} FROM {marked})"
            )
            parameters.append(seed)
            ctes.append(
                f"{stage} AS (SELECT * FROM {ranked} "
                f"WHERE NOT {match_column} OR {rank_column} <= ?)"
            )
            parameters.append(rule.limit)
            current = stage
            conditional_index += 1
            continue

        if isinstance(rule, GroupQuotaRule):
            current, group_parameters, group_ctes = _compile_group_quota(
                current,
                identity=identity,
                rule=rule,
                seed=seed,
            )
            ctes.extend(group_ctes)
            parameters.extend(group_parameters)
            continue

        if not isinstance(rule, TotalLimitRule):
            raise InvalidSamplingRuleError(f"unsupported sampling rule: {type(rule)!r}")

    sql = (
        f"WITH {', '.join(ctes)} SELECT {identity} AS {output} FROM {current} "
        f"ORDER BY HASH({identity}, ?), {identity}"
    )
    parameters.append(seed)
    total_limit = next(
        (rule for rule in program.rules if isinstance(rule, TotalLimitRule)),
        None,
    )
    if total_limit is not None:
        sql += " LIMIT ?"
        parameters.append(total_limit.limit)
    return CompiledDuckDbSampling(sql=sql, parameters=tuple(parameters))


def execute_duckdb_sampling(
    connection: duckdb.DuckDBPyConnection,
    source: DuckDbSamplingSource,
    *,
    program: SamplingProgram,
    seed: int,
    batch_rows: int,
) -> DuckDbSamplingExecution:
    """Execute a compiled program and stream selected identities as Arrow batches."""

    if (
        isinstance(batch_rows, bool)
        or not isinstance(batch_rows, int)
        or batch_rows <= 0
    ):
        raise InvalidSamplingRuleError("DuckDB sampling batch_rows must be positive")
    compiled = compile_duckdb_sampling(source, program=program, seed=seed)
    reader = connection.execute(
        compiled.sql, list(compiled.parameters)
    ).to_arrow_reader(batch_rows)
    return DuckDbSamplingExecution(reader=reader, compiled=compiled)


def _compile_dynamic_adder_ctes(
    reference_source: DuckDbSamplingSource,
    *,
    config: DynamicAdderConfig,
) -> tuple[list[str], list[DuckDbParameter]]:
    radius = validate_dynamic_adder_config(config)
    if config.match_mode is AdderMatchMode.ONE_TO_ONE:
        raise InvalidSamplingRuleError(
            "DuckDB spatial enrichment does not support order-dependent "
            "one_to_one adder matching; use any_reference"
        )
    if not reference_source.sql.strip():
        raise InvalidSamplingRuleError(
            "DuckDB reference-layer source SQL cannot be empty"
        )

    row_index = '"__sampling_spatial_row_index"'
    reference_index = '"__sampling_reference_index"'
    x = '"__sampling_x"'
    y = '"__sampling_y"'
    cell_x = '"__sampling_cell_x"'
    cell_y = '"__sampling_cell_y"'
    distance_squared = '"__sampling_distance_squared"'
    reference_identity = _quote_path(reference_source.identity_field)
    ctes = [
        (
            '"__sampling_adder_current_coordinates" AS ('
            f"SELECT {row_index}, "
            f"{_coordinate_expression('base', config.x_field)} AS {x}, "
            f"{_coordinate_expression('base', config.y_field)} AS {y} "
            'FROM "__sampling_spatial_base" AS base)'
        ),
        (
            '"__sampling_adder_current_points" AS ('
            f"SELECT *, FLOOR({x} / ?) AS {cell_x}, "
            f"FLOOR({y} / ?) AS {cell_y} "
            'FROM "__sampling_adder_current_coordinates")'
        ),
        f'"__sampling_adder_reference_raw" AS ({reference_source.sql})',
        (
            '"__sampling_adder_reference_indexed" AS ('
            f"SELECT *, ROW_NUMBER() OVER (ORDER BY {reference_identity}) - 1 "
            f"AS {reference_index} "
            'FROM "__sampling_adder_reference_raw")'
        ),
        (
            '"__sampling_adder_reference_coordinates" AS ('
            f"SELECT {reference_index}, "
            f"{_coordinate_expression('reference', config.x_field)} AS {x}, "
            f"{_coordinate_expression('reference', config.y_field)} AS {y} "
            'FROM "__sampling_adder_reference_indexed" AS reference)'
        ),
        (
            '"__sampling_adder_reference_points" AS ('
            f"SELECT *, FLOOR({x} / ?) AS {cell_x}, "
            f"FLOOR({y} / ?) AS {cell_y} "
            'FROM "__sampling_adder_reference_coordinates")'
        ),
        (
            '"__sampling_adder_candidates" AS ('
            f"SELECT current.{row_index}, reference.{reference_index}, "
            f"POWER(current.{x} - reference.{x}, 2) + "
            f"POWER(current.{y} - reference.{y}, 2) AS {distance_squared} "
            'FROM "__sampling_adder_current_points" AS current '
            'JOIN "__sampling_adder_reference_points" AS reference ON '
            f"ABS(current.{cell_x} - reference.{cell_x}) <= 1 AND "
            f"ABS(current.{cell_y} - reference.{cell_y}) <= 1 AND "
            f"POWER(current.{x} - reference.{x}, 2) + "
            f"POWER(current.{y} - reference.{y}, 2) <= ?)"
        ),
        (
            '"__sampling_adder_matches" AS ('
            f"SELECT {row_index}, {reference_index}, SQRT({distance_squared}) "
            f"AS {_quote_identifier(DYNAMIC_ADDER_DISTANCE_FIELD)} "
            'FROM "__sampling_adder_candidates" '
            f"QUALIFY ROW_NUMBER() OVER (PARTITION BY {row_index} "
            f"ORDER BY {distance_squared}, {reference_index}) = 1)"
        ),
        (
            '"__sampling_adder_features" AS ('
            f"SELECT current.{row_index}, "
            f"CASE WHEN matched.{reference_index} IS NULL THEN 1 ELSE 0 END "
            f"AS {_quote_identifier(DYNAMIC_ADDER_FIELD)}, "
            f"matched.{_quote_identifier(DYNAMIC_ADDER_DISTANCE_FIELD)}, "
            f"matched.{reference_index} "
            f"AS {_quote_identifier(DYNAMIC_ADDER_REFERENCE_INDEX_FIELD)} "
            'FROM "__sampling_adder_current_points" AS current '
            'LEFT JOIN "__sampling_adder_matches" AS matched '
            f"ON matched.{row_index} = current.{row_index})"
        ),
    ]
    parameters: list[DuckDbParameter] = [
        radius,
        radius,
        *reference_source.parameters,
        radius,
        radius,
        radius * radius,
    ]
    return ctes, parameters


def _compile_dynamic_cluster_ctes(
    *,
    config: DynamicClusterConfig,
) -> tuple[list[str], list[DuckDbParameter]]:
    radius = validate_dynamic_cluster_config(config)
    row_index = '"__sampling_spatial_row_index"'
    neighbor_index = '"__sampling_neighbor_index"'
    x = '"__sampling_x"'
    y = '"__sampling_y"'
    cell_x = '"__sampling_cell_x"'
    cell_y = '"__sampling_cell_y"'
    neighbor_count = _quote_identifier(DYNAMIC_CLUSTER_NEIGHBOR_COUNT_FIELD)
    component = '"__sampling_component"'
    cluster_id = _quote_identifier(DYNAMIC_CLUSTER_ID_FIELD)
    ctes = [
        (
            '"__sampling_cluster_coordinates" AS ('
            f"SELECT {row_index}, "
            f"{_coordinate_expression('base', config.x_field)} AS {x}, "
            f"{_coordinate_expression('base', config.y_field)} AS {y} "
            'FROM "__sampling_spatial_base" AS base)'
        ),
        (
            '"__sampling_cluster_points" AS ('
            f"SELECT *, FLOOR({x} / ?) AS {cell_x}, "
            f"FLOOR({y} / ?) AS {cell_y} "
            'FROM "__sampling_cluster_coordinates")'
        ),
        (
            '"__sampling_cluster_neighbors" AS ('
            f"SELECT current.{row_index}, candidate.{row_index} AS {neighbor_index} "
            'FROM "__sampling_cluster_points" AS current '
            'JOIN "__sampling_cluster_points" AS candidate ON '
            f"ABS(current.{cell_x} - candidate.{cell_x}) <= 1 AND "
            f"ABS(current.{cell_y} - candidate.{cell_y}) <= 1 AND "
            f"POWER(current.{x} - candidate.{x}, 2) + "
            f"POWER(current.{y} - candidate.{y}, 2) <= ?)"
        ),
        (
            '"__sampling_cluster_counts" AS ('
            f"SELECT {row_index}, COUNT(*) AS {neighbor_count} "
            'FROM "__sampling_cluster_neighbors" '
            f"GROUP BY {row_index})"
        ),
        (
            '"__sampling_cluster_core" AS ('
            f"SELECT {row_index}, {neighbor_count} "
            'FROM "__sampling_cluster_counts" '
            f"WHERE {neighbor_count} >= ?)"
        ),
        (
            '"__sampling_cluster_core_edges" AS ('
            f"SELECT neighbors.{row_index}, neighbors.{neighbor_index} "
            'FROM "__sampling_cluster_neighbors" AS neighbors '
            'JOIN "__sampling_cluster_core" AS current_core '
            f"ON current_core.{row_index} = neighbors.{row_index} "
            'JOIN "__sampling_cluster_core" AS neighbor_core '
            f"ON neighbor_core.{row_index} = neighbors.{neighbor_index})"
        ),
        (
            f'"__sampling_cluster_components"({row_index}, {component}) '
            f"USING KEY ({row_index}) AS ("
            f"SELECT {row_index}, {row_index} AS {component} "
            'FROM "__sampling_cluster_core" '
            "UNION ALL ("
            f"SELECT DISTINCT ON (previous.{row_index}) previous.{row_index}, "
            f"initial.{component} "
            'FROM recurring."__sampling_cluster_components" AS previous, '
            '"__sampling_cluster_components" AS initial, '
            '"__sampling_cluster_core_edges" AS edge '
            f"WHERE edge.{row_index} = previous.{row_index} AND "
            f"edge.{neighbor_index} = initial.{row_index} AND "
            f"initial.{component} < previous.{component} "
            f"ORDER BY previous.{row_index}, initial.{component}))"
        ),
        (
            '"__sampling_cluster_component_ids" AS ('
            f"SELECT {row_index}, DENSE_RANK() OVER (ORDER BY {component}) "
            f"AS {cluster_id} "
            'FROM "__sampling_cluster_components")'
        ),
        (
            '"__sampling_cluster_border_ids" AS ('
            f"SELECT neighbors.{row_index}, "
            f"MIN(core_component.{cluster_id}) AS {cluster_id} "
            'FROM "__sampling_cluster_neighbors" AS neighbors '
            'JOIN "__sampling_cluster_component_ids" AS core_component '
            f"ON core_component.{row_index} = neighbors.{neighbor_index} "
            f"GROUP BY neighbors.{row_index})"
        ),
        (
            '"__sampling_cluster_features" AS ('
            f"SELECT counts.{row_index}, "
            f"CASE WHEN core_component.{row_index} IS NOT NULL THEN 1 "
            f"WHEN border.{row_index} IS NOT NULL THEN 1 ELSE 0 END "
            f"AS {_quote_identifier(DYNAMIC_CLUSTER_FIELD)}, "
            f"COALESCE(core_component.{cluster_id}, border.{cluster_id}, 0) "
            f"AS {cluster_id}, counts.{neighbor_count}, "
            f"CASE WHEN core_component.{row_index} IS NOT NULL THEN 'core' "
            f"WHEN border.{row_index} IS NOT NULL THEN 'border' ELSE 'noise' END "
            f"AS {_quote_identifier(DYNAMIC_CLUSTER_ROLE_FIELD)} "
            'FROM "__sampling_cluster_counts" AS counts '
            'LEFT JOIN "__sampling_cluster_component_ids" AS core_component '
            f"ON core_component.{row_index} = counts.{row_index} "
            'LEFT JOIN "__sampling_cluster_border_ids" AS border '
            f"ON border.{row_index} = counts.{row_index})"
        ),
    ]
    return ctes, [radius, radius, radius * radius, config.minimum_points]


def _coordinate_expression(alias: str, field: str) -> str:
    coordinate = f"{alias}.{_quote_path(field)}"
    converted = f"TRY_CAST({coordinate} AS DOUBLE)"
    duckdb_type = f"TYPEOF({coordinate})"
    numeric_type = (
        f"({duckdb_type} IN ('TINYINT', 'SMALLINT', 'INTEGER', 'BIGINT', "
        "'HUGEINT', 'UTINYINT', 'USMALLINT', 'UINTEGER', 'UBIGINT', "
        f"'UHUGEINT', 'FLOAT', 'DOUBLE') OR STARTS_WITH({duckdb_type}, 'DECIMAL'))"
    )
    return (
        f"CASE WHEN NOT {numeric_type} OR {converted} IS NULL "
        f"OR NOT ISFINITE({converted}) "
        "THEN error('dynamic spatial coordinates must be finite numbers') "
        f"ELSE {converted} END"
    )


def _compile_group_quota(
    current: str,
    *,
    identity: str,
    rule: GroupQuotaRule,
    seed: int,
) -> tuple[str, list[DuckDbParameter], list[str]]:
    _validate_group_rule(rule)
    group_columns = [_quote_path(field) for field in rule.group_by]
    partition = ", ".join(group_columns)
    rank_column = '"__sampling_group_rank"'
    population_column = '"__sampling_group_population"'
    target_column = '"__sampling_group_target"'
    ranked = '"__sampling_group_ranked"'
    targeted = '"__sampling_group_targeted"'
    selected = '"__sampling_group_selected"'
    parameters: list[DuckDbParameter] = [seed]
    ctes = [
        f"{ranked} AS (SELECT *, "
        f"ROW_NUMBER() OVER (PARTITION BY {partition} "
        f"ORDER BY HASH({identity}, ?), {identity}) AS {rank_column}, "
        f"COUNT(*) OVER (PARTITION BY {partition}) AS {population_column} "
        f"FROM {current})"
    ]

    branches: list[str] = []
    for target in rule.targets:
        comparisons = []
        for column, value in zip(group_columns, target.group, strict=True):
            comparisons.append(f"{column} IS NOT DISTINCT FROM ?")
            parameters.append(value)
        target_sql, target_parameters = _quota_expression(
            rule,
            target.amount,
            population_column,
        )
        parameters.extend(target_parameters)
        branches.append(f"WHEN {' AND '.join(comparisons)} THEN {target_sql}")
    others_sql, others_parameters = _quota_expression(
        rule,
        rule.others_amount,
        population_column,
    )
    parameters.extend(others_parameters)
    ctes.append(
        f"{targeted} AS (SELECT *, CASE {' '.join(branches)} "
        f"ELSE {others_sql} END AS {target_column} FROM {ranked})"
    )
    if rule.shortfall is ShortfallPolicy.ERROR:
        effective_target = (
            f"CASE WHEN {target_column} <= {population_column} THEN {target_column} "
            "ELSE error('sampling group quota exceeds the available population') END"
        )
    else:
        effective_target = f"LEAST({target_column}, {population_column})"
    ctes.append(
        f"{selected} AS (SELECT * FROM {targeted} "
        f"WHERE {rank_column} <= {effective_target})"
    )
    return selected, parameters, ctes


def _quota_expression(
    rule: GroupQuotaRule,
    amount: int | float,
    population_column: str,
) -> tuple[str, list[DuckDbParameter]]:
    if rule.unit is QuotaUnit.COUNT:
        return "?", [int(amount)]
    rounding = {
        Rounding.FLOOR: "FLOOR",
        Rounding.CEIL: "CEIL",
        Rounding.NEAREST: "ROUND",
    }[rule.rounding]
    return f"{rounding}({population_column} * ? / 100.0)", [float(amount)]


def _validate_group_rule(rule: GroupQuotaRule) -> None:
    if not rule.group_by or any(not field.strip() for field in rule.group_by):
        raise InvalidSamplingRuleError(
            "group rules require at least one non-empty group_by field"
        )
    groups = [target.group for target in rule.targets]
    if len(set(groups)) != len(groups):
        raise InvalidSamplingRuleError("group quota rules cannot repeat a group")
    if any(len(group) != len(rule.group_by) for group in groups):
        raise InvalidSamplingRuleError("group target width must match group_by width")
    amounts = [*(target.amount for target in rule.targets), rule.others_amount]
    if rule.unit is QuotaUnit.COUNT:
        if any(
            isinstance(amount, bool) or not isinstance(amount, int) or amount < 0
            for amount in amounts
        ):
            raise InvalidSamplingRuleError(
                "count targets must be non-negative integers"
            )
        return
    if any(
        isinstance(amount, bool)
        or not isinstance(amount, int | float)
        or not math.isfinite(float(amount))
        or float(amount) < 0
        or float(amount) > 100
        for amount in amounts
    ):
        raise InvalidSamplingRuleError(
            "sample ratio targets must be finite percentages between zero and 100"
        )


def _compile_condition_set(
    condition_set: ConditionSet,
) -> tuple[str, list[DuckDbParameter]]:
    if not condition_set.conditions:
        raise InvalidSamplingRuleError("condition sets cannot be empty")
    expressions: list[str] = []
    parameters: list[DuckDbParameter] = []
    for condition in condition_set.conditions:
        if isinstance(condition, ConditionSet):
            expression, child_parameters = _compile_condition_set(condition)
        else:
            expression, child_parameters = _compile_condition(condition)
        expressions.append(f"({expression})")
        parameters.extend(child_parameters)
    joiner = " AND " if condition_set.match is MatchMode.ALL else " OR "
    return joiner.join(expressions), parameters


def _compile_condition(
    condition: Condition,
) -> tuple[str, list[DuckDbParameter]]:
    column = _quote_path(condition.field)
    operator = condition.operator
    if operator is ConditionOperator.EQ:
        return f"{column} IS NOT DISTINCT FROM ?", [_scalar_parameter(condition.value)]
    if operator is ConditionOperator.NE:
        return f"{column} IS DISTINCT FROM ?", [_scalar_parameter(condition.value)]
    if operator in (ConditionOperator.IN, ConditionOperator.NOT_IN):
        values = _sequence_value(condition)
        if not values:
            return ("TRUE" if operator is ConditionOperator.NOT_IN else "FALSE"), []
        matches = " OR ".join(f"{column} IS NOT DISTINCT FROM ?" for _ in values)
        expression = f"({matches})"
        if operator is ConditionOperator.NOT_IN:
            expression = f"NOT {expression}"
        return expression, [_scalar_parameter(value) for value in values]
    if operator is ConditionOperator.BETWEEN:
        bounds = _sequence_value(condition)
        if len(bounds) != 2:
            raise InvalidSamplingRuleError(
                "between conditions require exactly two boundary values"
            )
        return (
            f"{column} BETWEEN ? AND ?",
            [_scalar_parameter(bounds[0]), _scalar_parameter(bounds[1])],
        )
    sql_operator = {
        ConditionOperator.GT: ">",
        ConditionOperator.GTE: ">=",
        ConditionOperator.LT: "<",
        ConditionOperator.LTE: "<=",
    }.get(operator)
    if sql_operator is None:
        raise InvalidSamplingRuleError(f"unsupported condition operator: {operator!r}")
    return f"{column} {sql_operator} ?", [_scalar_parameter(condition.value)]


def _scalar_parameter(value: object) -> bool | int | float | str | None:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise InvalidSamplingRuleError("sampling condition values must be scalar")


def _sequence_value(condition: Condition) -> tuple[object, ...]:
    if not isinstance(condition.value, tuple):
        raise InvalidSamplingRuleError(
            f"operator {condition.operator.value!r} requires a tuple value"
        )
    return condition.value


def _quote_path(path: str) -> str:
    parts = path.split(".")
    if any(not part for part in parts):
        raise InvalidSamplingRuleError(f"invalid sampling field path: {path!r}")
    return ".".join(_quote_identifier(part) for part in parts)


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise InvalidSamplingRuleError(f"invalid DuckDB identifier: {identifier!r}")
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'
