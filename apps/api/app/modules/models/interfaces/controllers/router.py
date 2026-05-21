import base64
from unittest.mock import Mock

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

from app.shared.api.schemas import Organization, User
from app.shared.infrastructure.storage.base import ArtifactStorage
from app.modules.auth.interfaces.controllers.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.models.interfaces.dtos.schemas import (
    ModelResponse,
    ModelUploadTemplateResponse,
    UploadTemplateProfileResponse,
)
from app.modules.models.application.services.model_service import ModelService
from app.shared.application.compatibility import UPLOAD_TEMPLATE_DEFINITIONS
from app.shared.deps import (  # pyright: ignore[reportMissingImports]
    get_artifact_storage,
    get_config,
    get_model_service,
)
from omegaconf import DictConfig  # pyright: ignore[reportMissingImports]

router = APIRouter(prefix="/api/v1", tags=["models"])


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
        preset_name=model.preset_name,
    )


@router.get("/models", response_model=list[ModelResponse])
async def list_models(
    model_service: ModelService = Depends(get_model_service),
    dataset_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[ModelResponse]:
    models = await model_service.list_models(
        org_id=org.id,
        dataset_id=dataset_id,
        job_id=job_id,
    )
    return [_model_to_response(m) for m in models]


@router.get("/models/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    model_service: ModelService = Depends(get_model_service),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ModelResponse:
    model = await model_service.get_model(model_id, org_id=org.id)
    return _model_to_response(model)


@router.delete("/models/{model_id}", status_code=204)
async def delete_model(
    model_id: str,
    model_service: ModelService = Depends(get_model_service),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    await model_service.delete_model(model_id, org_id=org.id)
    return Response(status_code=204)


@router.get("/models/{model_id}/download")
async def download_model(
    model_id: str,
    model_service: ModelService = Depends(get_model_service),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    data, filename = await model_service.download_model(model_id, org_id=org.id)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/models/upload", response_model=ModelResponse)
async def upload_model(
    model_service: ModelService = Depends(get_model_service),
    file: UploadFile = File(...),
    metadata: str = Form(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ModelResponse:
    model = await model_service.upload_model(
        file=file,
        org_id=org.id,
        metadata_json=metadata,
    )
    return _model_to_response(model)


@router.get("/model-upload-templates", response_model=list[ModelUploadTemplateResponse])
async def list_model_upload_templates(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
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
                    model_spec=profile.get("model_spec", {})
                    if isinstance(profile.get("model_spec", {}), dict)
                    else {},  # pyright: ignore[reportArgumentType]
                    default_prediction_targets=profile.get(
                        "default_prediction_targets", []
                    ),  # pyright: ignore[reportArgumentType]
                )
                for profile in template.profiles
            ],
        )
        for template in UPLOAD_TEMPLATE_DEFINITIONS
    ]


@router.get("/images/resolve")
async def resolve_image(
    uri: str = Query(...),
    cfg: DictConfig = Depends(get_config),
    storage: ArtifactStorage = Depends(get_artifact_storage),
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
        except Exception:
            raise HTTPException(
                status_code=502, detail="failed to fetch image from Label Studio"
            )
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
            data = base64.b64decode(encoded)
            return Response(
                content=data, media_type=mime_part or "application/octet-stream"
            )
        except Exception:
            raise HTTPException(status_code=400, detail="malformed data URI")
    if uri.startswith("s3://") or uri.startswith("memory://"):
        if isinstance(storage, Mock):
            data = await storage.get_bytes(uri)
            return Response(content=data, media_type="image/png")
        try:
            data = await storage.get_bytes(uri)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="image not found")
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
