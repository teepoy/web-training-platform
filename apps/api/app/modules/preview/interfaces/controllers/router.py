from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query

from app.modules.auth.interfaces.controllers.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.preview.api.deps import (
    LabelStudioClientDep,
    PreviewServiceDep,
    RepositoryDep,
)
from app.modules.preview.interfaces.dtos.schemas import (
    CreatePreviewSessionRequest,
    PersistStatusResponse,
    PreviewItemResponse,
    PreviewItemsResponse,
    PreviewSessionResponse,
    StartPersistRequest,
)
from app.shared.api.schemas import Organization, User

router = APIRouter(prefix="/api/v1", tags=["preview"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentOrgDep = Annotated[Organization, Depends(get_current_org)]


@router.post("/preview-sessions", response_model=PreviewSessionResponse)
async def create_preview_session(
    payload: CreatePreviewSessionRequest,
    preview_service: PreviewServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> PreviewSessionResponse:
    try:
        session = await preview_service.create_session(
            collection_ref=payload.collection_ref,
            user_id=str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return PreviewSessionResponse(
        session_id=session.session_id,
        collection_ref=session.collection_ref,
        classification_enabled=False,
        estimated_total=session.estimated_total,
        loaded_count=len(session.items),
        next_cursor=session.next_cursor,
        has_more=session.next_cursor is not None,
    )


@router.get("/preview-sessions/{session_id}", response_model=PreviewSessionResponse)
async def get_preview_session(
    session_id: str,
    preview_service: PreviewServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> PreviewSessionResponse:
    session = await preview_service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail="preview session expired or not found"
        )
    return PreviewSessionResponse(
        session_id=session.session_id,
        collection_ref=session.collection_ref,
        classification_enabled=False,
        estimated_total=session.estimated_total,
        loaded_count=len(session.items),
        next_cursor=session.next_cursor,
        has_more=session.next_cursor is not None,
    )


@router.get("/preview-sessions/{session_id}/items", response_model=PreviewItemsResponse)
async def list_preview_items(
    session_id: str,
    preview_service: PreviewServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> PreviewItemsResponse:
    session = await preview_service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail="preview session expired or not found"
        )
    try:
        page = await preview_service.fetch_next_page(session_id, cursor, limit)
    except KeyError:
        raise HTTPException(
            status_code=404, detail="preview session expired or not found"
        )
    return PreviewItemsResponse(
        items=[
            PreviewItemResponse(
                upstream_item_id=item.upstream_item_id,
                image_uris=item.image_uris,
                metadata=item.metadata,
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
        estimated_total=page.estimated_total,
    )


@router.post(
    "/preview-sessions/{session_id}/persist",
    response_model=PersistStatusResponse,
)
async def start_preview_persist(
    session_id: str,
    payload: StartPersistRequest,
    preview_service: PreviewServiceDep,
    repo: RepositoryDep,
    ls_client: LabelStudioClientDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> PersistStatusResponse:
    session = await preview_service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail="preview session expired or not found"
        )
    from app.modules.preview.domain.entities.preview import PreviewPersistScope

    valid_scopes = ("entire_collection", "loaded_items_only")
    if payload.scope not in valid_scopes:
        raise HTTPException(status_code=422, detail=f"invalid scope: {payload.scope}")
    scope = cast(PreviewPersistScope, payload.scope)
    status = await preview_service.start_persist(
        session_id=session_id,
        scope=scope,
        dataset_repo=repo,
        label_studio_client=ls_client,
    )
    return PersistStatusResponse(
        dataset_id=status.dataset_id,
        persist_session_id=status.persist_session_id,
        status=status.status,
        imported_count=status.imported_count,
        remaining_count=status.remaining_count,
        error=status.error,
    )


@router.get(
    "/preview-sessions/{session_id}/persist-status",
    response_model=PersistStatusResponse,
)
async def get_preview_persist_status(
    session_id: str,
    preview_service: PreviewServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> PersistStatusResponse:
    status = await preview_service.get_persist_status(session_id)
    if status is None:
        raise HTTPException(
            status_code=404, detail="no persist operation found for this session"
        )
    return PersistStatusResponse(
        dataset_id=status.dataset_id,
        persist_session_id=status.persist_session_id,
        status=status.status,
        imported_count=status.imported_count,
        remaining_count=status.remaining_count,
        error=status.error,
    )
