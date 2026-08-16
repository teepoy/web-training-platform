from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from pydantic import BaseModel

from app.modules.automations.domain.models import AutomationRunOverview


class AutomationRunOverviewResponse(BaseModel):
    id: str
    run_source: str
    target_type: str
    target_id: str
    target_label: str
    recipe_kind: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    needs_attention: bool
    retry_supported: bool
    detail: str | None

    @classmethod
    def from_domain(cls, value: AutomationRunOverview) -> AutomationRunOverviewResponse:
        return cls(**asdict(value))
