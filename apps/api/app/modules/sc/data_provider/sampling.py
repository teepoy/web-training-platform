from __future__ import annotations

from sampling_rules import (
    ClusterCountRule,
    ClusterPercentageRule,
    DuckDbSamplingSource,
    ExcludeClassCodesRule,
    FinalClassDistributionRule,
    FinalClassTarget,
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
    Rounding,
    SizeField,
    SizeRangeRule,
    compile_duckdb_review_sampling,
)

from app.modules.sc.data_provider.schemas import (
    ScSamplingClassCodesRule,
    ScSamplingCountRule,
    ScSamplingFinalClassDistributionRule,
    ScSamplingLargeDefectRule,
    ScSamplingLimitRule,
    ScSamplingPercentageRule,
    ScSamplingProgramRequest,
    ScSamplingRequireImageRule,
    ScSamplingSelectionRequest,
    ScSamplingSizeRangeRule,
    ScSqlParameter,
)
from app.modules.sc.data_provider.sql_policy import ValidatedScSql, validate_sc_sql


_MISSING_FINAL_CLASS = "__unclassified__"


def compile_sc_sampling_query(
    source_sql: ValidatedScSql,
    source_parameters: list[ScSqlParameter],
    selection: ScSamplingSelectionRequest,
) -> tuple[ValidatedScSql, list[ScSqlParameter]]:
    """Compile the SC review-rule transport with the production table engine."""

    compiled = compile_duckdb_review_sampling(
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


def _sampling_program(request: ScSamplingProgramRequest) -> ReviewSamplingProgram:
    rules = []
    for rule in request.rules:
        if isinstance(rule, ScSamplingPercentageRule):
            rounding = Rounding(rule.rounding)
            if rule.type == "cluster_percentage":
                rules.append(ClusterPercentageRule(rule.percentage, rounding=rounding))
            elif rule.type == "repeater_percentage":
                rules.append(RepeaterPercentageRule(rule.percentage, rounding=rounding))
            else:
                rules.append(RandomPercentageRule(rule.percentage, rounding=rounding))
        elif isinstance(rule, ScSamplingClassCodesRule):
            class_codes = tuple(rule.class_codes)
            rules.append(
                ExcludeClassCodesRule(class_codes)
                if rule.type == "exclude_class_codes"
                else IncludeClassCodesRule(class_codes)
            )
        elif isinstance(rule, ScSamplingLimitRule):
            limit_rules = {
                "per_die_limit": PerDieLimitRule,
                "per_cluster_limit": PerClusterLimitRule,
                "per_repeater_limit": PerRepeaterLimitRule,
                "per_wafer_limit": PerWaferLimitRule,
            }
            rules.append(limit_rules[rule.type](rule.limit))
        elif isinstance(rule, ScSamplingCountRule):
            count_rules = {
                "cluster_count": ClusterCountRule,
                "repeater_count": RepeaterCountRule,
                "random_count": RandomCountRule,
            }
            rules.append(count_rules[rule.type](rule.count))
        elif isinstance(rule, ScSamplingRequireImageRule):
            rules.append(RequireImageRule())
        elif isinstance(rule, ScSamplingSizeRangeRule):
            rules.append(
                SizeRangeRule(
                    size_field=SizeField(rule.size_field),
                    minimum=rule.minimum,
                    maximum=rule.maximum,
                )
            )
        elif isinstance(rule, ScSamplingLargeDefectRule):
            size_field = SizeField(rule.size_field)
            if rule.type == "large_defect_percentage":
                assert rule.percentage is not None and rule.rounding is not None
                rules.append(
                    LargeDefectPercentageRule(
                        percentage=rule.percentage,
                        rounding=Rounding(rule.rounding),
                        size_field=size_field,
                        minimum=rule.minimum,
                    )
                )
            else:
                assert rule.count is not None
                rules.append(
                    LargeDefectCountRule(
                        count=rule.count,
                        size_field=size_field,
                        minimum=rule.minimum,
                    )
                )
        elif isinstance(rule, ScSamplingFinalClassDistributionRule):
            rules.append(
                FinalClassDistributionRule(
                    count=rule.count,
                    targets=tuple(
                        FinalClassTarget(
                            value=(
                                None
                                if target.value == _MISSING_FINAL_CLASS
                                else target.value
                            ),
                            percentage=target.percentage,
                        )
                        for target in rule.targets
                    ),
                )
            )
    return ReviewSamplingProgram(rules=tuple(rules))
