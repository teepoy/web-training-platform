from __future__ import annotations

from injector import inject

from app.modules.automations.domain.models import AutomationRunOverview
from app.modules.automations.domain.repository import AutomationOverviewRepository


_RECIPE_KINDS = {"discovery", "backfill", "retry", "prediction"}
_STATUSES = {
    "pending",
    "running",
    "completed",
    "failed",
    "partial",
    "needs_attention",
}


class AutomationOverviewService:
    @inject
    def __init__(self, repository: AutomationOverviewRepository) -> None:
        self._repository = repository

    async def list_runs(
        self,
        org_id: str,
        *,
        offset: int,
        limit: int,
        status: str | None,
        recipe_kind: str | None,
        query: str | None,
    ) -> tuple[list[AutomationRunOverview], int]:
        if status is not None and status not in _STATUSES:
            raise ValueError("Unknown automation status filter")
        if recipe_kind is not None and recipe_kind not in _RECIPE_KINDS:
            raise ValueError("Unknown automation recipe filter")
        normalized_query = query.strip() if query is not None else None
        return await self._repository.list_runs(
            org_id,
            offset=offset,
            limit=limit,
            status=status,
            recipe_kind=recipe_kind,
            query=normalized_query or None,
        )
