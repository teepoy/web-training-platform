from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from croniter import croniter


class CreateScheduleRequest(BaseModel):
    name: str
    flow_name: str
    cron: str
    parameters: dict = Field(default_factory=dict)
    description: str = ""

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError("invalid cron expression")
        return v


class UpdateScheduleRequest(BaseModel):
    name: str | None = None
    cron: str | None = None
    parameters: dict | None = None
    description: str | None = None
    is_schedule_active: bool | None = None

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v is not None and not croniter.is_valid(v):
            raise ValueError("invalid cron expression")
        return v


class ScheduleResponse(BaseModel):
    id: str
    name: str
    flow_name: str
    cron: str | None = None
    parameters: dict = Field(default_factory=dict)
    description: str = ""
    is_schedule_active: bool = True
    created: str | None = None
    updated: str | None = None
    prefect_deployment_id: str


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
    parameters: dict = Field(default_factory=dict)


class RunLogResponse(BaseModel):
    id: str | None = None
    flow_run_id: str | None = None
    level: int
    timestamp: str
    message: str
