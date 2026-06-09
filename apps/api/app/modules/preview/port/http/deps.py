from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.preview.app.services.preview_service import PreviewService
from app.modules.preview.app.services.preview_store import PreviewStore
from app.modules.preview.app.services.preview_upstream import UpstreamAdapter
from app.shared.db.sql_repository import SqlRepository
from app.shared.domain.protocols import LabelStudioClient


def get_preview_store(request: Request) -> PreviewStore:
    return request.app.state.app_context.preview.preview_store


def get_preview_upstream(request: Request) -> UpstreamAdapter:
    return request.app.state.app_context.preview.preview_upstream


def get_preview_service(
    store: Annotated[PreviewStore, Depends(get_preview_store)],
    upstream: Annotated[UpstreamAdapter, Depends(get_preview_upstream)],
) -> PreviewService:
    return PreviewService(store=store, upstream=upstream)


def get_repository(request: Request) -> SqlRepository:
    return SqlRepository(
        session_factory=request.app.state.app_context.shared.session_factory
    )


def get_label_studio_client(request: Request) -> LabelStudioClient:
    return request.app.state.app_context.shared.label_studio_client


def get_dataset_storage_factory(request: Request) -> DatasetStorageFactory:
    return request.app.state.app_context.datasets.dataset_storage_factory


PreviewServiceDep = Annotated[PreviewService, Depends(get_preview_service)]
DatasetStorageFactoryDep = Annotated[
    DatasetStorageFactory, Depends(get_dataset_storage_factory)
]
RepositoryDep = Annotated[SqlRepository, Depends(get_repository)]
LabelStudioClientDep = Annotated[LabelStudioClient, Depends(get_label_studio_client)]
