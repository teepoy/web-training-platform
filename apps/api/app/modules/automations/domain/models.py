from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AutomationRunOverview:
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
