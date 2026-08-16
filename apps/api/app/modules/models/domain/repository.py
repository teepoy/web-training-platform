from __future__ import annotations

from typing import Literal, Protocol

from app.shared.api.schemas import ArtifactRef, CreatorSummary, Model

ModelSortField = Literal["name", "source", "trainer", "creator", "created_at"]
ModelSourceType = Literal["dataset", "collection"]
SortDirection = Literal["asc", "desc"]


class ModelRepository(Protocol):
    async def list_models(
        self,
        org_id: str,
        dataset_id: str | None = None,
        job_id: str | None = None,
        query: str | None = None,
        creator_id: str | None = None,
        source_type: ModelSourceType | None = None,
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
        sort_by: ModelSortField = "created_at",
        sort_order: SortDirection = "desc",
    ) -> tuple[list[Model], int]: ...

    async def list_model_creators(self, org_id: str) -> list[CreatorSummary]: ...

    async def get_model(
        self,
        artifact_id: str,
        org_id: str,
        *,
        include_public: bool = True,
    ) -> Model | None: ...

    async def rename_model(
        self, artifact_id: str, org_id: str, name: str
    ) -> Model | None: ...

    async def delete_artifact(self, artifact_id: str) -> bool: ...

    async def get_training_job_context(
        self, job_id: str, org_id: str
    ) -> tuple[str, str] | None: ...

    async def add_artifacts(
        self, job_id: str, artifacts: list[ArtifactRef]
    ) -> None: ...
