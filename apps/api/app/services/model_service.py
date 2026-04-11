from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.domain.models import ArtifactRef, Model
from app.services.compatibility import validate_upload_metadata

if TYPE_CHECKING:
    from app.repositories.sql_repository import SqlRepository
    from app.storage.interfaces import ArtifactStorage


class ModelService:
    """Service for managing trained model artifacts."""

    def __init__(
        self,
        repository: SqlRepository,
        artifact_storage: ArtifactStorage,
    ) -> None:
        self.repository = repository
        self.artifact_storage = artifact_storage

    async def list_models(
        self,
        org_id: str,
        dataset_id: str | None = None,
        job_id: str | None = None,
    ) -> list[Model]:
        """List all model artifacts, optionally filtered by dataset or job."""
        artifacts = await self.repository.list_models(
            org_id=org_id,
            dataset_id=dataset_id,
            job_id=job_id,
        )
        return artifacts

    async def get_model(self, artifact_id: str, org_id: str) -> Model:
        """Get a single model by ID."""
        model = await self.repository.get_model(artifact_id, org_id)
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")
        return model

    async def delete_model(self, artifact_id: str, org_id: str) -> None:
        """Delete a model artifact."""
        model = await self.repository.get_model(artifact_id, org_id)
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")

        # Delete from storage
        try:
            await self.artifact_storage.delete(model.uri)
        except Exception:
            # Storage deletion may fail if URI is placeholder or already deleted
            pass

        # Delete from database
        await self.repository.delete_artifact(artifact_id)

    async def download_model(self, artifact_id: str, org_id: str) -> tuple[bytes, str]:
        """Download model bytes and return (bytes, filename)."""
        model = await self.repository.get_model(artifact_id, org_id)
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")

        try:
            data = await self.artifact_storage.get_bytes(model.uri)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Model file not found in storage: {e}")

        # Determine filename
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
        """Upload an external model file."""
        try:
            raw_metadata = json.loads(metadata_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"invalid upload metadata: {exc}")
        if not isinstance(raw_metadata, dict):
            raise HTTPException(status_code=400, detail="upload metadata must be a JSON object")

        try:
            upload_metadata = validate_upload_metadata(raw_metadata)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        name = str(upload_metadata.get("name", "")).strip()
        format = str(upload_metadata.get("format", "")).strip()
        job_id = str(upload_metadata.get("job_id", "")).strip() or job_id

        # Read file content
        content = await file.read()
        file_size = len(content)

        # Compute hash
        file_hash = hashlib.sha256(content).hexdigest()

        # Generate artifact ID
        artifact_id = str(uuid4())

        # Store in object storage
        object_name = f"models/{org_id}/{artifact_id}/{name}"
        uri = await self.artifact_storage.put_bytes(
            object_name=object_name,
            data=content,
            content_type=file.content_type or "application/octet-stream",
        )

        # If no job_id provided, we need to create a placeholder job
        # For now, require job_id for uploaded models
        if job_id is None:
            raise HTTPException(
                status_code=400,
                detail="job_id is required for model upload (associate with existing training job)",
            )

        # Create artifact record
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
                **upload_metadata.get("compatibility", {}),
                "model_spec": upload_metadata.get("model_spec", {}),
                "framework": str(upload_metadata.get("model_spec", {}).get("framework", "")),
                "architecture": str(upload_metadata.get("model_spec", {}).get("architecture", "")),
                "base_model": str(upload_metadata.get("model_spec", {}).get("base_model", "")),
            },
        )

        await self.repository.add_artifacts(job_id, [artifact])

        # Fetch the full model with job context
        return await self.get_model(artifact_id, org_id)

    async def create_model_from_training(
        self,
        job_id: str,
        model_bytes: bytes,
        name: str,
        format: str,
        org_id: str,
    ) -> ArtifactRef:
        """Create a model artifact from training job output."""
        file_size = len(model_bytes)
        file_hash = hashlib.sha256(model_bytes).hexdigest()
        artifact_id = str(uuid4())

        # Store in object storage
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
