from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.modules.jobs.schedules.domain.validation import (
    validate_cron_expression,
    validate_iana_timezone,
)


class CreateScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    flow_name: str = Field(min_length=1, max_length=255)
    cron: str
    timezone: str = "UTC"
    parameters: dict[str, object] = Field(default_factory=dict)
    description: str = ""

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        return validate_cron_expression(v)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return validate_iana_timezone(value)


class UpdateScheduleRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    cron: str | None = None
    timezone: str | None = None
    parameters: dict[str, object] | None = None
    description: str | None = None
    is_schedule_active: bool | None = None

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        return None if v is None else validate_cron_expression(v)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return None if value is None else validate_iana_timezone(value)


class ScheduleCapabilityResponse(BaseModel):
    flow_name: str
    deployment_name: str


class ScheduleResponse(BaseModel):
    id: str
    name: str
    flow_name: str
    cron: str | None = None
    timezone: str
    parameters: dict[str, object] = Field(default_factory=dict)
    description: str = ""
    is_schedule_active: bool = True
    created: str | None = None
    updated: str | None = None
    prefect_deployment_id: str | None = None
    prefect_deployment_url: str | None = None


class RunResponse(BaseModel):
    id: str
    name: str
    deployment_id: str | None = None
    flow_name: str | None = None
    state_type: str | None = None
    state_name: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    total_run_time: float | None = None
    parameters: dict[str, object] = Field(default_factory=dict)


class RunLogResponse(BaseModel):
    id: str | None = None
    flow_run_id: str | None = None
    level: int
    timestamp: str
    message: str
