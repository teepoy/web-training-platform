from __future__ import annotations

from typing import Protocol

from fastapi import UploadFile

from app.shared.api.schemas import ArtifactRef, CreatorSummary, Model
from app.modules.models.domain.repository import (
    ModelSortField,
    ModelSourceType,
    SortDirection,
)


class ModelCatalogPort(Protocol):
    async def get_model(
        self,
        artifact_id: str,
        org_id: str,
    ) -> Model | None: ...

    async def get_org_model(
        self,
        artifact_id: str,
        org_id: str,
    ) -> Model | None: ...

    async def list_models(
        self,
        org_id: str,
        dataset_id: str | None = None,
    ) -> list[Model]: ...


class ModelManagementPort(Protocol):
    async def list_models(
        self,
        org_id: str,
        dataset_id: str | None = None,
        job_id: str | None = None,
        query: str | None = None,
        creator_id: str | None = None,
        source_type: ModelSourceType | None = None,
        compatible_view_ids: tuple[str, ...] | None = None,
        sort_by: ModelSortField = "created_at",
        sort_order: SortDirection = "desc",
    ) -> list[Model]: ...

    async def list_models_paginated(
        self,
        org_id: str,
        dataset_id: str | None = None,
        job_id: str | None = None,
        *,
        offset: int = 0,
        limit: int | None = 50,
        query: str | None = None,
        creator_id: str | None = None,
        source_type: ModelSourceType | None = None,
        compatible_view_ids: tuple[str, ...] | None = None,
        sort_by: ModelSortField = "created_at",
        sort_order: SortDirection = "desc",
    ) -> tuple[list[Model], int]: ...

    async def list_model_creators(self, org_id: str) -> list[CreatorSummary]: ...

    async def get_model(self, artifact_id: str, org_id: str) -> Model: ...

    async def rename_model(
        self,
        artifact_id: str,
        org_id: str,
        name: str,
        current_user_id: str,
    ) -> Model: ...

    async def delete_model(
        self,
        artifact_id: str,
        org_id: str,
        current_user_id: str,
    ) -> None: ...

    async def download_model(
        self, artifact_id: str, org_id: str
    ) -> tuple[bytes, str]: ...

    async def prepare_model_download(
        self, artifact_id: str, org_id: str
    ) -> tuple[str, str, int]: ...

    async def upload_model(
        self,
        file: UploadFile,
        org_id: str,
        metadata_json: str,
        current_user_id: str,
    ) -> Model: ...

    async def create_model_from_training(
        self,
        job_id: str,
        model_bytes: bytes,
        name: str,
        format: str,
        org_id: str,
    ) -> ArtifactRef: ...


__all__ = ["ModelCatalogPort", "ModelManagementPort"]
