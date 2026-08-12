from __future__ import annotations

from typing import Protocol

from app.shared.api.schemas import ArtifactRef, CreatorSummary, Model


class ModelRepository(Protocol):
    async def list_models(
        self,
        org_id: str,
        dataset_id: str | None = None,
        job_id: str | None = None,
        query: str | None = None,
        creator_id: str | None = None,
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

    async def list_artifact_uris_by_job(self, job_id: str) -> list[tuple[str, str]]: ...

    async def delete_artifacts_by_ids(self, artifact_ids: list[str]) -> None: ...

    async def add_artifacts(
        self, job_id: str, artifacts: list[ArtifactRef]
    ) -> None: ...
