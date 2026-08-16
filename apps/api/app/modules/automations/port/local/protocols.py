from __future__ import annotations

from typing import Protocol

from app.modules.automations.domain.models import AutomationRunOverview


class AutomationOverviewPort(Protocol):
    async def list_runs(
        self,
        org_id: str,
        *,
        offset: int,
        limit: int,
        status: str | None,
        recipe_kind: str | None,
        query: str | None,
    ) -> tuple[list[AutomationRunOverview], int]: ...
