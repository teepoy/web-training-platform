from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.modules.auth.port.http.deps import get_current_org, get_current_user
from app.modules.automations.port.http.deps import AutomationOverviewDep
from app.modules.automations.port.http.schemas import AutomationRunOverviewResponse
from app.shared.api.schemas import Organization, PaginatedResponse, User


router = APIRouter(prefix="/api/v1/automations", tags=["automations"])


@router.get("", response_model=PaginatedResponse[AutomationRunOverviewResponse])
async def list_automation_runs(
    service: AutomationOverviewDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None, max_length=32),
    kind: str | None = Query(default=None, max_length=32),
    q: str | None = Query(default=None, max_length=200),
) -> PaginatedResponse[AutomationRunOverviewResponse]:
    del current_user
    try:
        runs, total = await service.list_runs(
            org.id,
            offset=offset,
            limit=limit,
            status=status,
            recipe_kind=kind,
            query=q,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaginatedResponse(
        items=[AutomationRunOverviewResponse.from_domain(run) for run in runs],
        total=total,
    )
