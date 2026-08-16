from __future__ import annotations

from sampling_rules import (
    Condition,
    ConditionOperator,
    ConditionSet,
    ConditionalLimitRule,
    DuckDbSamplingSource,
    GroupQuotaRule,
    GroupTarget,
    MatchMode,
    QuotaUnit,
    Rounding,
    SamplingProgram,
    ShortfallPolicy,
    TotalLimitRule,
    compile_duckdb_sampling,
)

from app.modules.sc.data_provider.schemas import (
    ScSamplingProgramRequest,
    ScSamplingSelectionRequest,
    ScSqlParameter,
)
from app.modules.sc.data_provider.sql_policy import ValidatedScSql, validate_sc_sql


_MISSING_GROUP_VALUES = {
    "annotation_label": "__unlabeled__",
    "prediction_label": "__no_prediction__",
    "final_class": "__unclassified__",
}


def compile_sc_sampling_query(
    source_sql: ValidatedScSql,
    source_parameters: list[ScSqlParameter],
    selection: ScSamplingSelectionRequest,
) -> tuple[ValidatedScSql, list[ScSqlParameter]]:
    """Compile the SC transport shape with the production sampling library."""

    compiled = compile_duckdb_sampling(
        DuckDbSamplingSource(
            sql=source_sql.sql,
            parameters=tuple(source_parameters),
            identity_field="map_id",
            output_field="defect_id",
        ),
        program=_sampling_program(selection.program),
        seed=selection.seed,
    )
    return validate_sc_sql(compiled.sql), list(compiled.parameters)


def _sampling_program(request: ScSamplingProgramRequest) -> SamplingProgram:
    rules = []
    if request.conditional.enabled:
        rules.append(
            ConditionalLimitRule(
                where=_equals(
                    request.conditional.field,
                    _transport_group_value(
                        request.conditional.field,
                        request.conditional.value,
                    ),
                ),
                limit=request.conditional.limit,
            )
        )
    if request.group.enabled:
        rules.append(
            GroupQuotaRule(
                group_by=(request.group.field,),
                unit=QuotaUnit(request.group.unit),
                targets=tuple(
                    GroupTarget(
                        group=(
                            _transport_group_value(request.group.field, target.value),
                        ),
                        amount=target.amount,
                    )
                    for target in request.group.targets
                ),
                others_amount=request.group.others_amount,
                rounding=Rounding(request.group.rounding),
                shortfall=ShortfallPolicy.TAKE_AVAILABLE,
            )
        )
    if request.total.enabled:
        rules.append(TotalLimitRule(limit=request.total.limit))
    return SamplingProgram(rules=tuple(rules))


def _equals(field: str, value: bool | int | float | str | None) -> ConditionSet:
    return ConditionSet(
        conditions=(
            Condition(
                field=field,
                operator=ConditionOperator.EQ,
                value=value,
            ),
        ),
        match=MatchMode.ALL,
    )


def _transport_group_value(
    field: str,
    value: bool | int | float | str | None,
) -> bool | int | float | str | None:
    if value == _MISSING_GROUP_VALUES.get(field):
        return None
    return value
