from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.preview.application.services.preview_service import PreviewService
from app.modules.preview.application.services.preview_store import PreviewStore
from app.modules.preview.application.services.preview_upstream import UpstreamAdapter
from app.shared.db.sql_repository import SqlRepository
from app.shared.domain.protocols import LabelStudioClient


def get_preview_store(request: Request) -> PreviewStore:
    return request.app.state.container.preview_store


def get_preview_upstream(request: Request) -> UpstreamAdapter:
    return request.app.state.container.preview_upstream


def get_preview_service(
    store: Annotated[PreviewStore, Depends(get_preview_store)],
    upstream: Annotated[UpstreamAdapter, Depends(get_preview_upstream)],
) -> PreviewService:
    return PreviewService(store=store, upstream=upstream)


def get_repository(request: Request) -> SqlRepository:
    return SqlRepository(session_factory=request.app.state.container.session_factory)


def get_label_studio_client(request: Request) -> LabelStudioClient:
    return request.app.state.container.label_studio_client


PreviewServiceDep = Annotated[PreviewService, Depends(get_preview_service)]
RepositoryDep = Annotated[SqlRepository, Depends(get_repository)]
LabelStudioClientDep = Annotated[LabelStudioClient, Depends(get_label_studio_client)]
