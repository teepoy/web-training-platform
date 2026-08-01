from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


ScSqlScalar: TypeAlias = bool | int | float | str | None
ScSqlArray: TypeAlias = list[bool] | list[int] | list[float] | list[str]
ScSqlParameter: TypeAlias = ScSqlScalar | ScSqlArray


class ScSqlQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sql: str
    parameters: list[ScSqlParameter]

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
