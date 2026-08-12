from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from injector import inject

from app.shared.api.schemas import ArtifactRef, CreatorSummary, Model
from app.shared.application.compatibility import validate_upload_metadata
from app.modules.models.domain.repository import ModelRepository
from app.shared.domain.protocols import ArtifactStorage


class ModelService:
    @inject
    def __init__(
        self,
        repository: ModelRepository,
        artifact_storage: ArtifactStorage,
    ) -> None:
        self.repository = repository
        self.artifact_storage = artifact_storage

    async def list_models(
        self,
        org_id: str,
        dataset_id: str | None = None,
        job_id: str | None = None,
        query: str | None = None,
        creator_id: str | None = None,
    ) -> list[Model]:
        return await self.repository.list_models(
            org_id=org_id,
            dataset_id=dataset_id,
            job_id=job_id,
            query=query,
            creator_id=creator_id,
        )

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
    ) -> tuple[list[Model], int]:
        return await self.repository.list_models_paginated(
            org_id=org_id,
            dataset_id=dataset_id,
            job_id=job_id,
            offset=offset,
            limit=limit,
            query=query,
            creator_id=creator_id,
        )

    async def list_model_creators(self, org_id: str) -> list[CreatorSummary]:
        return await self.repository.list_model_creators(org_id)

    async def get_model(self, artifact_id: str, org_id: str) -> Model:
        model = await self.repository.get_model(artifact_id, org_id)
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")
        return model

    async def rename_model(
        self,
        artifact_id: str,
        org_id: str,
        name: str,
        current_user_id: str,
    ) -> Model:
        normalized_name = name.strip()
        if not normalized_name:
            raise HTTPException(status_code=422, detail="Model name is required")
        existing = await self.repository.get_model(
            artifact_id,
            org_id,
            include_public=False,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="Model not found")
        if existing.created_by != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="Only the model creator can rename this model",
            )
        model = await self.repository.rename_model(artifact_id, org_id, normalized_name)
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")
        return model

    async def delete_model(
        self,
        artifact_id: str,
        org_id: str,
        current_user_id: str,
    ) -> None:
        model = await self.repository.get_model(
            artifact_id,
            org_id,
            include_public=False,
        )
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")
        if model.created_by != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="Only the model creator can delete this model",
            )

        job_artifacts = await self.repository.list_artifact_uris_by_job(model.job_id)

        for _, uri in job_artifacts:
            await self.artifact_storage.delete(uri)

        artifact_ids = [aid for aid, _ in job_artifacts]
        await self.repository.delete_artifacts_by_ids(artifact_ids)

    async def download_model(self, artifact_id: str, org_id: str) -> tuple[bytes, str]:
        model = await self.repository.get_model(artifact_id, org_id)
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")

        try:
            data = await self.artifact_storage.get_bytes(model.uri)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="Model file not found in storage",
            ) from exc

        filename = model.name or f"model_{artifact_id}"
        if model.format:
            ext_map = {
                "pytorch": ".pt",
                "onnx": ".onnx",
                "safetensors": ".safetensors",
                "keras": ".keras",
            }
            ext = ext_map.get(model.format, "")
            if ext and not filename.endswith(ext):
                filename += ext

        return data, filename

    async def upload_model(
        self,
        file: UploadFile,
        org_id: str,
        metadata_json: str,
        job_id: str | None = None,
        dataset_id: str | None = None,
    ) -> Model:
        try:
            raw_metadata = json.loads(metadata_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid upload metadata: {exc}"
            )
        if not isinstance(raw_metadata, dict):
            raise HTTPException(
                status_code=400, detail="upload metadata must be a JSON object"
            )

        try:
            upload_metadata = validate_upload_metadata(raw_metadata)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        name = str(upload_metadata.get("name", "")).strip()
        format = str(upload_metadata.get("format", "")).strip()
        job_id = str(upload_metadata.get("job_id", "")).strip() or job_id

        content = await file.read()
        file_size = len(content)
        file_hash = hashlib.sha256(content).hexdigest()
        artifact_id = str(uuid4())

        object_name = f"models/{org_id}/{artifact_id}/{name}"
        uri = await self.artifact_storage.put_bytes(
            object_name=object_name,
            data=content,
            content_type=file.content_type or "application/octet-stream",
        )

        if job_id is None:
            raise HTTPException(
                status_code=400,
                detail="job_id is required for model upload (associate with existing training job)",
            )

        raw_spec = upload_metadata.get("model_spec", {})
        if not isinstance(raw_spec, dict):
            raw_spec = {}
        compatibility_raw = upload_metadata.get("compatibility", {})
        compatibility_dict: dict[str, Any] = (
            compatibility_raw if isinstance(compatibility_raw, dict) else {}
        )
        artifact = ArtifactRef(
            id=artifact_id,
            uri=uri,
            kind="model",
            name=name,
            file_size=file_size,
            file_hash=file_hash,
            format=format,
            created_at=datetime.now(UTC),
            metadata={
                "uploaded": True,
                "original_filename": file.filename,
                "template_id": upload_metadata.get("template_id"),
                "profile_id": upload_metadata.get("profile_id"),
                **compatibility_dict,
                "model_spec": raw_spec,
                "framework": str(raw_spec.get("framework", "")),
                "architecture": str(raw_spec.get("architecture", "")),
                "base_model": str(raw_spec.get("base_model", "")),
            },
        )

        await self.repository.add_artifacts(job_id, [artifact])

        return await self.get_model(artifact_id, org_id)

    async def create_model_from_training(
        self,
        job_id: str,
        model_bytes: bytes,
        name: str,
        format: str,
        org_id: str,
    ) -> ArtifactRef:
        file_size = len(model_bytes)
        file_hash = hashlib.sha256(model_bytes).hexdigest()
        artifact_id = str(uuid4())

        object_name = f"models/{org_id}/{job_id}/{name}"

        content_type_map = {
            "pytorch": "application/octet-stream",
            "onnx": "application/octet-stream",
            "safetensors": "application/octet-stream",
        }
        content_type = content_type_map.get(format, "application/octet-stream")

        uri = await self.artifact_storage.put_bytes(
            object_name=object_name,
            data=model_bytes,
            content_type=content_type,
        )

        artifact = ArtifactRef(
            id=artifact_id,
            uri=uri,
            kind="model",
            name=name,
            file_size=file_size,
            file_hash=file_hash,
            format=format,
            created_at=datetime.now(UTC),
            metadata={"source": "training"},
        )

        await self.repository.add_artifacts(job_id, [artifact])
        return artifact
