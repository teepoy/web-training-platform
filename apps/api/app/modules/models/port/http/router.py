import base64
import binascii
from typing import Annotated, Any, cast

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)

from app.shared.api.schemas import CreatorSummary, Organization, PaginatedResponse, User
from app.shared.domain.protocols import ArtifactStorage
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.models.port.http.schemas import (
    ModelResponse,
    ModelUploadTemplateResponse,
    UpdateModelRequest,
    UploadTemplateProfileResponse,
)
from app.modules.models.port.local import ModelManagementPort
from app.shared.application.compatibility import UPLOAD_TEMPLATE_DEFINITIONS
from app.modules.models.port.http.deps import (
    get_artifact_storage,
    get_config,
    get_model_service,
)
from omegaconf import DictConfig

router = APIRouter(prefix="/api/v1", tags=["models"])

ModelServiceDep = Annotated[ModelManagementPort, Depends(get_model_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentOrgDep = Annotated[Organization, Depends(get_current_org)]


def _model_to_response(model) -> ModelResponse:
    return ModelResponse(
        id=model.id,
        uri=model.uri,
        kind=model.kind,
        name=model.name,
        file_size=model.file_size,
        file_hash=model.file_hash,
        format=model.format,
        created_at=model.created_at,
        metadata=model.metadata,
        job_id=model.job_id,
        dataset_id=model.dataset_id,
        dataset_name=model.dataset_name,
        collection_id=model.collection_id,
        collection_revision_id=model.collection_revision_id,
        collection_name=model.collection_name,
        trainer_name=model.trainer_name,
        created_by=model.created_by,
        creator_name=model.creator_name,
    )


@router.get("/models", response_model=PaginatedResponse[ModelResponse])
async def list_models(
    model_service: ModelServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    dataset_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=200),
    creator_id: str | None = Query(default=None, max_length=255),
) -> PaginatedResponse[ModelResponse]:
    models, total = await model_service.list_models_paginated(
        org_id=org.id,
        dataset_id=dataset_id,
        job_id=job_id,
        offset=offset,
        limit=limit,
        query=q,
        creator_id=creator_id,
    )
    return PaginatedResponse(
        items=[_model_to_response(model) for model in models],
        total=total,
    )


@router.get("/models/creators", response_model=list[CreatorSummary])
async def list_model_creators(
    model_service: ModelServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> list[CreatorSummary]:
    return await model_service.list_model_creators(org.id)


@router.get("/models/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    model_service: ModelServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> ModelResponse:
    model = await model_service.get_model(model_id, org_id=org.id)
    return _model_to_response(model)


@router.patch("/models/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: str,
    payload: UpdateModelRequest,
    model_service: ModelServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> ModelResponse:
    model = await model_service.rename_model(
        model_id,
        org_id=org.id,
        name=payload.name,
        current_user_id=current_user.id,
    )
    return _model_to_response(model)


@router.delete("/models/{model_id}", status_code=204)
async def delete_model(
    model_id: str,
    model_service: ModelServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> Response:
    await model_service.delete_model(
        model_id,
        org_id=org.id,
        current_user_id=current_user.id,
    )
    return Response(status_code=204)


@router.get("/models/{model_id}/download")
async def download_model(
    model_id: str,
    model_service: ModelServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> Response:
    data, filename = await model_service.download_model(model_id, org_id=org.id)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/models/upload", response_model=ModelResponse)
async def upload_model(
    model_service: ModelServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    file: UploadFile = File(...),
    metadata: str = Form(...),
) -> ModelResponse:
    model = await model_service.upload_model(
        file=file,
        org_id=org.id,
        metadata_json=metadata,
    )
    return _model_to_response(model)


@router.get("/model-upload-templates", response_model=list[ModelUploadTemplateResponse])
async def list_model_upload_templates(
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> list[ModelUploadTemplateResponse]:
    return [
        ModelUploadTemplateResponse(
            id=template.id,
            name=template.name,
            dataset_types=list(template.dataset_types),
            task_types=list(template.task_types),
            label_space_mode=template.label_space_mode,
            requires_embedding_metadata=template.requires_embedding_metadata,
            profiles=[
                UploadTemplateProfileResponse(
                    id=str(profile.get("id", "")),
                    name=str(profile.get("name", "")),
                    model_spec=cast("dict[str, Any]", profile.get("model_spec", {}))
                    if isinstance(profile.get("model_spec", {}), dict)
                    else {},
                    default_prediction_targets=cast(
                        "list[str]", profile.get("default_prediction_targets", [])
                    ),
                )
                for profile in template.profiles
            ],
        )
        for template in UPLOAD_TEMPLATE_DEFINITIONS
    ]


@router.get("/images/resolve")
async def resolve_image(
    cfg: Annotated[DictConfig, Depends(get_config)],
    storage: Annotated[ArtifactStorage, Depends(get_artifact_storage)],
    uri: str = Query(...),
) -> Response:
    if uri.startswith("http://") or uri.startswith("https://"):
        ls_url = str(cfg.label_studio.url).rstrip("/")
        if not (ls_url and uri.startswith(ls_url)):
            raise HTTPException(
                status_code=400, detail="http/https URIs are not allowed"
            )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(uri)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail="failed to fetch image from Label Studio"
            ) from exc
        content_type = resp.headers.get("content-type") or resp.headers.get(
            "Content-Type"
        )
        if not content_type:
            lower_uri = uri.lower()
            if lower_uri.endswith(".png"):
                content_type = "image/png"
            elif lower_uri.endswith(".gif"):
                content_type = "image/gif"
            elif lower_uri.endswith(".webp"):
                content_type = "image/webp"
            else:
                content_type = "image/jpeg"
        return Response(content=resp.content, media_type=content_type)
    if uri.startswith("data:"):
        try:
            header, encoded = uri.split(",", 1)
            mime_part = header.split(";")[0][len("data:") :]
            data = base64.b64decode(encoded, validate=True)
            return Response(
                content=data, media_type=mime_part or "application/octet-stream"
            )
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(
                status_code=400,
                detail="malformed data URI",
            ) from exc
    if uri.startswith("s3://") or uri.startswith("memory://"):
        try:
            data = await storage.get_bytes(uri)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="image not found",
            ) from exc
        lower_uri = uri.lower()
        if lower_uri.endswith(".png"):
            media_type = "image/png"
        elif lower_uri.endswith(".gif"):
            media_type = "image/gif"
        elif lower_uri.endswith(".webp"):
            media_type = "image/webp"
        else:
            media_type = "image/jpeg"
        return Response(content=data, media_type=media_type)
    raise HTTPException(status_code=400, detail="unsupported URI scheme")
