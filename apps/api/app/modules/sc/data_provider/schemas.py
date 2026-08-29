from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ScSqlScalar: TypeAlias = bool | int | float | str | None
ScSqlArray: TypeAlias = list[bool] | list[int] | list[float] | list[str]
ScSqlParameter: TypeAlias = ScSqlScalar | ScSqlArray


class ScClassifyLimitsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_rows: Annotated[int, Field(gt=0)]


class _ScSamplingRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class ScSamplingPercentageRule(_ScSamplingRule):
    type: Literal[
        "cluster_percentage",
        "repeater_percentage",
        "random_percentage",
    ]
    percentage: Annotated[float, Field(gt=0, le=100)]
    rounding: Literal["floor"]


class ScSamplingClassCodesRule(_ScSamplingRule):
    type: Literal["exclude_class_codes", "include_class_codes"]
    class_codes: Annotated[list[int], Field(alias="classCodes", min_length=1)]

    @field_validator("class_codes")
    @classmethod
    def validate_unique_class_codes(cls, values: list[int]) -> list[int]:
        if len(values) != len(set(values)):
            raise ValueError("sampling classCodes cannot contain duplicates")
        return values


class ScSamplingLimitRule(_ScSamplingRule):
    type: Literal[
        "per_die_limit",
        "per_cluster_limit",
        "per_repeater_limit",
        "per_wafer_limit",
    ]
    limit: Annotated[int, Field(ge=1)]


class ScSamplingCountRule(_ScSamplingRule):
    type: Literal["cluster_count", "repeater_count", "random_count"]
    count: Annotated[int, Field(ge=1)]


class ScSamplingRequireImageRule(_ScSamplingRule):
    type: Literal["require_image"]


class ScSamplingSizeRangeRule(_ScSamplingRule):
    type: Literal["size_range"]
    size_field: Literal["size_x", "size_y", "size_d", "area"] = Field(alias="sizeField")
    minimum: Annotated[float, Field(ge=0)]
    maximum: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def validate_bounds(self) -> ScSamplingSizeRangeRule:
        if self.maximum < self.minimum:
            raise ValueError("sampling size maximum must be >= minimum")
        return self


class ScSamplingLargeDefectRule(_ScSamplingRule):
    type: Literal["large_defect_percentage", "large_defect_count"]
    size_field: Literal["size_x", "size_y", "size_d", "area"] = Field(alias="sizeField")
    minimum: Annotated[float, Field(ge=0)]
    percentage: Annotated[float | None, Field(default=None, gt=0, le=100)]
    count: Annotated[int | None, Field(default=None, ge=1)]
    rounding: Literal["floor"] | None = None

    @model_validator(mode="after")
    def validate_mode_fields(self) -> ScSamplingLargeDefectRule:
        if self.type == "large_defect_percentage":
            if (
                self.percentage is None
                or self.rounding is None
                or self.count is not None
            ):
                raise ValueError(
                    "large_defect_percentage requires percentage and rounding only"
                )
        elif (
            self.count is None
            or self.percentage is not None
            or self.rounding is not None
        ):
            raise ValueError("large_defect_count requires count only")
        return self


class ScSamplingFinalClassTarget(_ScSamplingRule):
    value: str | None
    percentage: Annotated[float, Field(gt=0, le=100)]


class ScSamplingFinalClassDistributionRule(_ScSamplingRule):
    type: Literal["final_class_distribution"]
    count: Annotated[int, Field(ge=1)]
    targets: Annotated[list[ScSamplingFinalClassTarget], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_targets(self) -> ScSamplingFinalClassDistributionRule:
        values = [target.value for target in self.targets]
        if len(values) != len(set(values)):
            raise ValueError("final class targets cannot contain duplicate values")
        if abs(sum(target.percentage for target in self.targets) - 100) > 1e-6:
            raise ValueError("final class target percentages must total exactly 100")
        return self


ScReviewSamplingRule: TypeAlias = Annotated[
    ScSamplingPercentageRule
    | ScSamplingClassCodesRule
    | ScSamplingLimitRule
    | ScSamplingCountRule
    | ScSamplingRequireImageRule
    | ScSamplingSizeRangeRule
    | ScSamplingLargeDefectRule
    | ScSamplingFinalClassDistributionRule,
    Field(discriminator="type"),
]


class ScSamplingProgramRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    rules: Annotated[list[ScReviewSamplingRule], Field(min_length=1, max_length=17)]

    @model_validator(mode="after")
    def validate_bounded_program(self) -> ScSamplingProgramRequest:
        rule_types = [rule.type for rule in self.rules]
        if len(rule_types) != len(set(rule_types)):
            raise ValueError("sampling rule types cannot be enabled more than once")
        eligibility_types = {
            "exclude_class_codes",
            "require_image",
            "size_range",
            "include_class_codes",
        }
        if all(rule_type in eligibility_types for rule_type in rule_types):
            raise ValueError("sampling requires at least one selector or cap rule")
        return self


class ScSamplingSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    program: ScSamplingProgramRequest
    seed: Annotated[int, Field(ge=0)]


class ScSqlQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    description: Annotated[
        str,
        Field(
            min_length=1,
            max_length=120,
            pattern=r"^[a-z0-9][a-z0-9._:-]*$",
        ),
    ]
    sql: str
    parameters: list[ScSqlParameter]
    sampling: ScSamplingSelectionRequest | None = None

    @field_validator("parameters")
    @classmethod
    def validate_parameters(
        cls, parameters: list[ScSqlParameter]
    ) -> list[ScSqlParameter]:
        for index, parameter in enumerate(parameters):
            if not isinstance(parameter, list):
                continue
            if not parameter:
                raise ValueError(f"parameters[{index}] must not be an empty array")
            first_type = type(parameter[0])
            if any(type(item) is not first_type for item in parameter):
                raise ValueError(
                    f"parameters[{index}] must contain values of one JSON scalar type"
                )
        return parameters


class ScDataInvalidationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    revision: Annotated[int, Field(ge=0)]
    changed_kinds: list[Literal["annotation", "prediction", "samples", "images"]]


class ScSampleTableColumnDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
    title: Annotated[str, Field(min_length=1, max_length=80)]
    width: Annotated[int, Field(ge=60, le=600)]
    filter: Literal["set", "range"] | None
    visibility: Literal["default", "reclassify", "filter_only", "internal"]
    format: Literal["plain", "integer", "fixed_3"] = "plain"


class ScSampleTableDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: Literal["sc.sample-table.v1"]
    columns: tuple[ScSampleTableColumnDescriptor, ...]
