from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SensorDefinition(BaseModel):
    """Complete sensor definition loaded from a flat sensor YAML file."""

    id: str
    name: str
    description: str
    cron: str
    filter_schema: dict[str, Any] = Field(default_factory=dict)
    available_triggers: list[str] = Field(default_factory=list)
