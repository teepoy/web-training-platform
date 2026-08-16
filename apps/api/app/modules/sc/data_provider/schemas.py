from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ScSqlScalar: TypeAlias = bool | int | float | str | None
ScSqlArray: TypeAlias = list[bool] | list[int] | list[float] | list[str]
ScSqlParameter: TypeAlias = ScSqlScalar | ScSqlArray


class ScSamplingConditionalRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool
    field: str
    value: ScSqlScalar
    limit: Annotated[int, Field(ge=0)]


class ScSamplingGroupTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: ScSqlScalar
    amount: int | float


class ScSamplingGroupRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    enabled: bool
    field: str
    unit: Literal["count", "ratio"]
    targets: list[ScSamplingGroupTarget]
    others_amount: int | float = Field(alias="othersAmount")
    rounding: Literal["floor", "ceil", "nearest"]


class ScSamplingTotalRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool
    limit: Annotated[int, Field(ge=1)]


class ScSamplingProgramRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    conditional: ScSamplingConditionalRule
    group: ScSamplingGroupRule
    total: ScSamplingTotalRule

    @model_validator(mode="after")
    def validate_bounded_program(self) -> ScSamplingProgramRequest:
        if not self.group.enabled and not self.total.enabled:
            raise ValueError("sampling requires an enabled group rule or total limit")
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
