from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from injector import inject

from app.modules.models.domain.repository import ModelRepository
from app.modules.models.domain.repository import (
    CompatibleModelSpec,
    ModelSortField,
    ModelSourceType,
    SortDirection,
)
from app.modules.runtime.catalog import runtime_catalog
from app.modules.types.catalog import get_view_meta
from app.shared.api.schemas import ArtifactRef, CreatorSummary, Model
from app.shared.application.compatibility import validate_upload_metadata
from app.shared.domain.protocols import ArtifactStorage


_logger = logging.getLogger(__name__)
_MODEL_PACKAGE_SCHEMA = "platform.model-package"
_MODEL_PACKAGE_VERSION = 1
_MODEL_PACKAGE_MANIFEST_LIMIT = 64 * 1024


class ModelService:
    @inject
    def __init__(
        self,
        repository: ModelRepository,
        artifact_storage: ArtifactStorage,
        max_import_bytes: int,
    ) -> None:
        self.repository = repository
        self.artifact_storage = artifact_storage
        self.max_import_bytes = max_import_bytes

    @staticmethod
    def _copy_bounded_upload(
        source: IO[bytes],
        destination: Path,
        max_bytes: int,
    ) -> tuple[int, str]:
        source.seek(0)
        digest = hashlib.sha256()
        total = 0
        with destination.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Model import exceeds the configured byte limit",
                    )
                digest.update(chunk)
                target.write(chunk)
        return total, digest.hexdigest()

    @staticmethod
    def _file_digest(path: Path) -> tuple[int, str]:
        digest = hashlib.sha256()
        total = 0
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                digest.update(chunk)
        return total, digest.hexdigest()

    @classmethod
    def _extract_model_package(
        cls,
        source: IO[bytes],
        destination: Path,
        max_bytes: int,
    ) -> tuple[dict[str, Any], int, str, str]:
        source.seek(0)
        try:
            with zipfile.ZipFile(source) as package:
                entry_names = package.namelist()
                if len(entry_names) != 2 or set(entry_names) != {
                    "manifest.json",
                    "artifact",
                }:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Model package must contain exactly manifest.json "
                            "and artifact"
                        ),
                    )
                manifest_info = package.getinfo("manifest.json")
                if manifest_info.file_size > _MODEL_PACKAGE_MANIFEST_LIMIT:
                    raise HTTPException(
                        status_code=400,
                        detail="Model package manifest exceeds the size limit",
                    )
                manifest = json.loads(package.read(manifest_info))
                if not isinstance(manifest, dict):
                    raise HTTPException(
                        status_code=400,
                        detail="Model package manifest must be a JSON object",
                    )
                if (
                    manifest.get("schema") != _MODEL_PACKAGE_SCHEMA
                    or not isinstance(manifest.get("version"), int)
                    or isinstance(manifest.get("version"), bool)
                    or manifest.get("version") != _MODEL_PACKAGE_VERSION
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Unsupported model package schema or version",
                    )
                artifact_manifest = manifest.get("artifact")
                if not isinstance(artifact_manifest, dict):
                    raise HTTPException(
                        status_code=400,
                        detail="Model package manifest is missing artifact metadata",
                    )
                declared_size = artifact_manifest.get("size_bytes")
                declared_hash = artifact_manifest.get("sha256")
                if (
                    not isinstance(declared_size, int)
                    or isinstance(declared_size, bool)
                    or declared_size < 0
                    or not isinstance(declared_hash, str)
                    or len(declared_hash) != 64
                    or any(
                        character not in "0123456789abcdefABCDEF"
                        for character in declared_hash
                    )
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Model package artifact metadata is invalid",
                    )
                if declared_size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Model import exceeds the configured byte limit",
                    )
                artifact_info = package.getinfo("artifact")
                if artifact_info.file_size != declared_size:
                    raise HTTPException(
                        status_code=422,
                        detail="Model package artifact size does not match its manifest",
                    )
                with package.open(artifact_info) as artifact_source:
                    size, digest = cls._copy_bounded_upload(
                        artifact_source,
                        destination,
                        max_bytes,
                    )
        except HTTPException:
            raise
        except (
            json.JSONDecodeError,
            KeyError,
            NotImplementedError,
            OSError,
            RuntimeError,
            UnicodeError,
            zipfile.BadZipFile,
        ) as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid model package",
            ) from exc
        if size != declared_size or digest != declared_hash.lower():
            raise HTTPException(
                status_code=422,
                detail="Model package artifact checksum does not match its manifest",
            )
        raw_filename = str(artifact_manifest.get("filename", "artifact"))
        filename = Path(raw_filename).name or "artifact"
        return manifest, size, digest, filename

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
    ) -> list[Model]:
        return await self.repository.list_models(
            org_id=org_id,
            dataset_id=dataset_id,
            job_id=job_id,
            query=query,
            creator_id=creator_id,
            source_type=source_type,
            compatible_specs=self._compatible_model_specs(compatible_view_ids),
            sort_by=sort_by,
            sort_order=sort_order,
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
        source_type: ModelSourceType | None = None,
        compatible_view_ids: tuple[str, ...] | None = None,
        sort_by: ModelSortField = "created_at",
        sort_order: SortDirection = "desc",
    ) -> tuple[list[Model], int]:
        return await self.repository.list_models_paginated(
            org_id=org_id,
            dataset_id=dataset_id,
            job_id=job_id,
            offset=offset,
            limit=limit,
            query=query,
            creator_id=creator_id,
            source_type=source_type,
            compatible_specs=self._compatible_model_specs(compatible_view_ids),
            sort_by=sort_by,
            sort_order=sort_order,
        )

    @staticmethod
    def _compatible_model_specs(
        compatible_view_ids: tuple[str, ...] | None,
    ) -> tuple[CompatibleModelSpec, ...] | None:
        if compatible_view_ids is None:
            return None
        requested_views = set(compatible_view_ids)
        for view_id in requested_views:
            try:
                get_view_meta(view_id)
            except KeyError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown compatible view: {view_id}",
                ) from exc
        return tuple(
            CompatibleModelSpec(
                trainer_id=trainer.id,
                model_contract=trainer.output_model.contract,
                model_schema_version=trainer.output_model.schema_version,
            )
            for trainer in runtime_catalog.list_trainers()
            if trainer.input_view.view_id in requested_views
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

        if not await self.repository.delete_artifact(artifact_id):
            raise HTTPException(status_code=404, detail="Model not found")
        try:
            await self.artifact_storage.delete(model.uri)
        except Exception:
            _logger.warning(
                "Model metadata %s was deleted but artifact cleanup failed for %s",
                artifact_id,
                model.uri,
                exc_info=True,
            )

    async def download_model(self, artifact_id: str, org_id: str) -> tuple[bytes, str]:
        uri, filename, _ = await self.prepare_model_download(artifact_id, org_id)
        try:
            data = await self.artifact_storage.get_bytes(uri)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="Model file not found in storage",
            ) from exc
        return data, filename

    async def prepare_model_download(
        self, artifact_id: str, org_id: str
    ) -> tuple[str, str, int]:
        model = await self.repository.get_model(artifact_id, org_id)
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")

        try:
            size = await self.artifact_storage.get_size(model.uri)
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

        return model.uri, filename, size

    async def prepare_model_package_download(
        self, artifact_id: str, org_id: str
    ) -> tuple[Path, str, int]:
        model = await self.repository.get_model(artifact_id, org_id)
        if model is None:
            raise HTTPException(status_code=404, detail="Model not found")
        if not model.format:
            raise HTTPException(
                status_code=409,
                detail="Model has no format and cannot be exported as a package",
            )

        package_file = tempfile.NamedTemporaryFile(
            prefix="model-package-", suffix=".zip", delete=False
        )
        package_path = Path(package_file.name)
        package_file.close()
        try:
            with tempfile.TemporaryDirectory(prefix="model-export-") as directory:
                artifact_path = Path(directory) / "artifact"
                try:
                    await self.artifact_storage.get_file(model.uri, str(artifact_path))
                except FileNotFoundError as exc:
                    raise HTTPException(
                        status_code=404,
                        detail="Model file not found in storage",
                    ) from exc
                size, digest = await asyncio.to_thread(self._file_digest, artifact_path)
                if model.file_size is not None and model.file_size != size:
                    raise HTTPException(
                        status_code=409,
                        detail="Stored model size does not match its metadata",
                    )
                if model.file_hash is not None and model.file_hash != digest:
                    raise HTTPException(
                        status_code=409,
                        detail="Stored model checksum does not match its metadata",
                    )
                artifact_filename = (
                    Path(model.name or f"model_{artifact_id}").name or "artifact"
                )
                manifest = {
                    "schema": _MODEL_PACKAGE_SCHEMA,
                    "version": _MODEL_PACKAGE_VERSION,
                    "training_job_id": model.job_id,
                    "format": model.format,
                    "trainer_id": model.metadata.get("trainer_id"),
                    "model_contract": model.metadata.get("model_contract"),
                    "model_schema_version": model.metadata.get("model_schema_version"),
                    "artifact": {
                        "filename": artifact_filename,
                        "size_bytes": size,
                        "sha256": digest,
                    },
                }

                def write_package() -> None:
                    with zipfile.ZipFile(
                        package_path, mode="w", compression=zipfile.ZIP_STORED
                    ) as package:
                        package.writestr(
                            "manifest.json",
                            json.dumps(
                                manifest,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        )
                        package.write(artifact_path, arcname="artifact")

                await asyncio.to_thread(write_package)
        except Exception:
            package_path.unlink(missing_ok=True)
            raise
        package_stem = Path(model.name or artifact_id).name or artifact_id
        filename = f"{package_stem}.model-package.zip"
        return package_path, filename, package_path.stat().st_size

    async def upload_model(
        self,
        file: UploadFile,
        org_id: str,
        metadata_json: str,
        current_user_id: str,
        job_id: str | None = None,
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

        upload_metadata = dict(raw_metadata)
        if str(raw_metadata.get("template_id", "")).strip():
            try:
                upload_metadata = validate_upload_metadata(raw_metadata)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        name = str(upload_metadata.get("name", "")).strip()
        if not name:
            raise HTTPException(status_code=400, detail="model name is required")
        with tempfile.TemporaryDirectory(prefix="model-import-") as directory:
            upload_path = Path(directory) / "artifact"
            format = str(upload_metadata.get("format", "")).strip()
            job_id = str(upload_metadata.get("job_id", "")).strip() or job_id
            original_filename = file.filename
            package_import = not format and job_id is None
            if package_import:
                (
                    manifest,
                    file_size,
                    file_hash,
                    original_filename,
                ) = await asyncio.to_thread(
                    self._extract_model_package,
                    file.file,
                    upload_path,
                    self.max_import_bytes,
                )
                format = str(manifest.get("format", "")).strip()
                job_id = str(manifest.get("training_job_id", "")).strip() or None
                upload_metadata.update(
                    {
                        "format": format,
                        "job_id": job_id,
                        "trainer_id": manifest.get("trainer_id"),
                        "model_contract": manifest.get("model_contract"),
                        "model_schema_version": manifest.get("model_schema_version"),
                    }
                )
            else:
                file_size, file_hash = await asyncio.to_thread(
                    self._copy_bounded_upload,
                    file.file,
                    upload_path,
                    self.max_import_bytes,
                )
            if not format:
                raise HTTPException(status_code=400, detail="model format is required")
            if job_id is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "job_id is required for model upload "
                        "(associate with existing training job)"
                    ),
                )

            job_context = await self.repository.get_training_job_context(job_id, org_id)
            if job_context is None:
                raise HTTPException(status_code=404, detail="Training job not found")
            job_creator_id, trainer_id = job_context
            if job_creator_id != current_user_id:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Only the training job creator can upload its model artifacts"
                    ),
                )
            try:
                registered_trainer = runtime_catalog.get_trainer(trainer_id)
            except KeyError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Training job references unknown trainer '{trainer_id}'",
                ) from exc
            trainer = registered_trainer.metadata
            model_contract = trainer.output_model.contract
            model_schema_version = trainer.output_model.schema_version
            supplied_contract = upload_metadata.get("model_contract")
            supplied_schema_version = upload_metadata.get("model_schema_version")
            if supplied_contract is not None and supplied_contract != model_contract:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"model_contract must match training job output contract "
                        f"'{model_contract}'"
                    ),
                )
            if (
                supplied_schema_version is not None
                and supplied_schema_version != model_schema_version
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "model_schema_version must match training job output schema "
                        f"'{model_schema_version}'"
                    ),
                )

            try:
                await asyncio.to_thread(
                    registered_trainer.artifact_validator,
                    upload_path,
                    format,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            artifact_id = str(uuid4())
            object_name = f"models/{org_id}/{artifact_id}/{name}"
            uri = await self.artifact_storage.put_file(
                object_name=object_name,
                path=str(upload_path),
                content_type=(
                    "application/octet-stream"
                    if package_import
                    else file.content_type or "application/octet-stream"
                ),
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
                "original_filename": original_filename,
                "template_id": upload_metadata.get("template_id"),
                "profile_id": upload_metadata.get("profile_id"),
                "trainer_id": trainer_id,
                "model_contract": model_contract,
                "model_schema_version": model_schema_version,
                **compatibility_dict,
                "model_spec": raw_spec,
                "framework": str(raw_spec.get("framework", "")),
                "architecture": str(raw_spec.get("architecture", "")),
                "base_model": str(raw_spec.get("base_model", "")),
            },
        )

        try:
            await self.repository.add_artifacts(job_id, [artifact])
        except Exception:
            try:
                await self.artifact_storage.delete(uri)
            except Exception:
                _logger.warning(
                    "Failed to clean uploaded model artifact %s after persistence error",
                    uri,
                    exc_info=True,
                )
            raise

        return await self.get_model(artifact_id, org_id)

    async def create_model_from_training(
        self,
        job_id: str,
        model_bytes: bytes,
        name: str,
        format: str,
        org_id: str,
    ) -> ArtifactRef:
        job_context = await self.repository.get_training_job_context(job_id, org_id)
        if job_context is None:
            raise ValueError(
                f"Training job '{job_id}' not found in organization '{org_id}'"
            )
        _, trainer_id = job_context
        trainer = runtime_catalog.get_trainer_meta(trainer_id)
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
            metadata={
                "source": "training",
                "trainer_id": trainer_id,
                "model_contract": trainer.output_model.contract,
                "model_schema_version": trainer.output_model.schema_version,
            },
        )

        try:
            await self.repository.add_artifacts(job_id, [artifact])
        except Exception:
            try:
                await self.artifact_storage.delete(uri)
            except Exception:
                _logger.warning(
                    "Failed to clean trained model artifact %s after persistence error",
                    uri,
                    exc_info=True,
                )
            raise
        return artifact
