import base64
from typing import Annotated

import httpx
from dependency_injector.wiring import Provide, inject
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

from app.api.deps import get_current_org, get_current_user
from app.api.schemas import ModelResponse
from app.container import Container
from app.domain.models import Organization, User
from app.routers._common import get_container
from app.services.model_service import ModelService

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
@inject
async def list_models(
    model_service: Annotated[ModelService, Depends(Provide[Container.model_service])],
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
@inject
async def get_model(
    model_id: str,
    model_service: Annotated[ModelService, Depends(Provide[Container.model_service])],
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ModelResponse:
    model = await model_service.get_model(model_id, org_id=org.id)
    return _model_to_response(model)


@router.delete("/models/{model_id}", status_code=204)
@inject
async def delete_model(
    model_id: str,
    model_service: Annotated[ModelService, Depends(Provide[Container.model_service])],
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    await model_service.delete_model(model_id, org_id=org.id)
    return Response(status_code=204)


@router.get("/models/{model_id}/download")
@inject
async def download_model(
    model_id: str,
    model_service: Annotated[ModelService, Depends(Provide[Container.model_service])],
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
@inject
async def upload_model(
    model_service: Annotated[ModelService, Depends(Provide[Container.model_service])],
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


@router.get("/images/resolve")
async def resolve_image(
    uri: str = Query(...),
    c=Depends(get_container),
) -> Response:
    if uri.startswith("http://") or uri.startswith("https://"):
        cfg = c.config()
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
    # Handle data: URIs
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
    # Handle storage URIs (s3:// or memory://)
    if uri.startswith("s3://") or uri.startswith("memory://"):
        try:
            data = await c.artifact_storage().get_bytes(uri)
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
