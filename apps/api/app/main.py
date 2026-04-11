from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from app.api.schemas import (
    AddMemberRequest,
    AnnotationVersionResponse,
    BatchPredictionResponse,
    BulkAnnotationRequest,
    BulkCreateSampleRequest,
    BulkCreateSampleResponse,
    CreateAnnotationRequest,
    CreateDatasetRequest,
    CreateOrgRequest,
    CreateReviewActionRequest,
    CreateSampleRequest,
    CreateScheduleRequest,
    CreateTokenRequest,
    CreateTrainingJobRequest,
    DashboardResponse,
    ExportFormatResponse,
    ImportVqaJsonlResponse,
    JobQueueStats,
    LatestAnnotation,
    LoginRequest,
    LoginResponse,
    MemberResponse,
    ModelUploadTemplateResponse,
    MembershipResponse,
    ModelResponse,
    OrgResponse,
    PaginatedResponse,
    PredictionEventResponse,
    PredictionJobResponse,
    PredictionResultResponse,
    PredictSingleRequest,
    RecentJobSummary,
    RegisterRequest,
    ReviewActionResponse,
    RunLogResponse,
    RunPredictionRequest,
    RunResponse,
    SaveReviewAnnotationsRequest,
    SaveReviewAnnotationsResponse,
    ScheduleResponse,
    ServiceStatus,
    SampleWithLabels,
    SetPublicRequest,
    TaskTrackerDetailResponse,
    TaskTrackerSummaryResponse,
    TokenCreatedResponse,
    TokenResponse,
    UpdateAnnotationRequest,
    UpdateEmbedConfigRequest,
    UpdateLabelSpaceRequest,
    UpdateSampleImageResponse,
    UpdateScheduleRequest,
    UploadModelRequest,
    UploadTemplateProfileResponse,
    UserResponse,
    UserWithOrgsResponse,
    VersionExportRequest,
    WorkPoolStatus,
)
from app.api.deps import get_current_org, get_current_user, require_superadmin
from app.services.scheduler import SchedulerService, get_scheduler_service
from app.container import Container
from app.db.models import DatasetORM, OrgMembershipORM, OrganizationORM, PersonalAccessTokenORM, TrainingJobORM, UserORM
from app.db.session import init_db
from app.domain.models import Annotation, Dataset, DEFAULT_ORG_ID, Organization, Sample, TrainingEvent, TrainingJob, User
from app.domain.types import DatasetType, TaskType
from app.services.auth import create_access_token, create_personal_access_token, hash_password, verify_password
from app.services.compatibility import (
    UPLOAD_TEMPLATE_DEFINITIONS,
    validate_dataset_contract,
    validate_dataset_preset_training,
)
from app.services.label_studio import platform_annotation_to_ls
_logger = logging.getLogger(__name__)


def _infer_dataset_type(task_type: TaskType) -> DatasetType:
    if task_type == TaskType.VQA:
        return DatasetType.IMAGE_VQA
    return DatasetType.IMAGE_CLASSIFICATION


async def _sync_file_presets_to_db() -> None:
    registry = container.preset_registry()
    repo = container.repository()
    existing_default_org = await repo.get_organization(DEFAULT_ORG_ID)
    if existing_default_org is None:
        await repo.create_organization(
            OrganizationORM(
                id=DEFAULT_ORG_ID,
                name="Default",
                slug="default",
            )
        )
    existing = await repo.list_preset_ids()
    for spec in registry.list_presets():
        if spec.id in existing:
            continue
        legacy = registry.preset_to_api_dict(spec)
        await repo.ensure_preset_row(
            preset_id=spec.id,
            name=spec.name,
            model_spec=legacy.get("model_spec", {}) if isinstance(legacy.get("model_spec", {}), dict) else {},
            omegaconf_yaml=str(legacy.get("omegaconf_yaml", "")),
            dataloader_ref=str(legacy.get("dataloader_ref", "")),
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    cfg = container.config()
    if bool(cfg.db.auto_create):
        await init_db(container.db_engine())

    # Load file-backed preset registry
    registry = container.preset_registry()
    count = registry.load()
    _logger.info("Preset registry: %d presets loaded", count)
    await _sync_file_presets_to_db()

    yield


app = FastAPI(title="Online Finetune API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

container = Container()


def _make_ls_image_url(uri: str) -> str:
    """Convert platform image URI to LS-accessible URL."""
    from urllib.parse import quote
    if uri.startswith(("s3://", "memory://")):
        return f"/api/v1/images/resolve?uri={quote(uri, safe='')}"
    return uri  # data: URIs and http:// pass through


def _with_ls_url(dataset: Dataset) -> Dataset:
    """Compute ls_project_url at response time from config.
    
    Uses external_url (browser-facing) if available, falls back to url (internal).
    """
    cfg = container.config()
    # Prefer external_url for browser access, fall back to internal url
    ls_url = str(cfg.label_studio.external_url or cfg.label_studio.url).rstrip("/")
    if dataset.ls_project_id and ls_url:
        return dataset.model_copy(
            update={"ls_project_url": f"{ls_url}/projects/{dataset.ls_project_id}"}
        )
    return dataset


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/datasets", response_model=Dataset)
async def create_dataset(
    payload: CreateDatasetRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Dataset:
    dataset_type = payload.dataset_type or _infer_dataset_type(payload.task_spec.task_type)
    try:
        validate_dataset_contract(dataset_type, payload.task_spec.task_type, payload.task_spec.label_space)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # LS-first: create project, fail if LS fails
    try:
        from app.services.label_studio import LabelStudioClient as _LSC
        ls_client = container.label_studio_client()
        if payload.task_spec.task_type == TaskType.VQA:
            label_config = _LSC.generate_vqa_config()
        else:
            label_config = _LSC.generate_image_classification_config(
                payload.task_spec.label_space
            )
        project = await ls_client.create_project(payload.name, label_config)
        ls_project_id = str(project.get("id", ""))
        if not ls_project_id:
            raise HTTPException(status_code=502, detail="Label Studio project creation returned no ID.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Label Studio project creation failed: {exc}")
    dataset = Dataset(
        name=payload.name,
        dataset_type=dataset_type,
        task_spec=payload.task_spec,
        org_id=org.id,
        ls_project_id=ls_project_id,
    )
    dataset = await container.repository().create_dataset(dataset)
    return _with_ls_url(dataset)


@app.get("/api/v1/datasets", response_model=list[Dataset])
async def list_datasets(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[Dataset]:
    datasets = await container.repository().list_datasets(org_id=org.id)
    return [_with_ls_url(d) for d in datasets]


@app.get("/api/v1/datasets/{dataset_id}", response_model=Dataset)
async def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Dataset:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _with_ls_url(dataset)


@app.patch("/api/v1/datasets/{dataset_id}/label-space", response_model=Dataset)
async def update_label_space(
    dataset_id: str,
    payload: UpdateLabelSpaceRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Dataset:
    """Update the label space for a dataset. Also updates the Label Studio project config."""
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Update Label Studio project config with new labels
    if dataset.ls_project_id:
        try:
            from app.services.label_studio import LabelStudioClient as _LSC
            ls_client = container.label_studio_client()
            if dataset.task_spec.task_type == TaskType.VQA:
                label_config = _LSC.generate_vqa_config()
            else:
                label_config = _LSC.generate_image_classification_config(payload.label_space)
            await ls_client.update_project(int(dataset.ls_project_id), label_config=label_config)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to update Label Studio project: {exc}")

    # Update the task_spec with the new label_space
    new_task_spec = {
        "task_type": dataset.task_spec.task_type,
        "label_space": payload.label_space,
    }
    updated = await container.repository().update_dataset_task_spec(dataset_id, new_task_spec)
    if updated is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _with_ls_url(updated)


@app.post("/api/v1/datasets/{dataset_id}/samples", response_model=Sample)
async def create_sample(
    dataset_id: str,
    payload: CreateSampleRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Sample:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if not dataset.ls_project_id:
        raise HTTPException(status_code=500, detail="Dataset has no Label Studio project — cannot create sample.")
    # LS-first: create task before persisting sample (avoid orphan rows on LS failure)
    try:
        ls_client = container.label_studio_client()
        image_url = _make_ls_image_url(payload.image_uris[0]) if payload.image_uris else ""
        task_data = {"image": image_url}
        if dataset.task_spec.task_type == TaskType.VQA:
            task_data["question"] = str(payload.metadata.get("question", ""))
        task = await ls_client.create_task(
            int(dataset.ls_project_id), task_data
        )
        ls_task_id = task.get("id")
        if ls_task_id is None:
            raise HTTPException(status_code=502, detail="Label Studio task creation returned no ID.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Label Studio task creation failed: {exc}")
    sample = Sample(dataset_id=dataset_id, image_uris=payload.image_uris, metadata=payload.metadata, ls_task_id=int(ls_task_id))
    sample = await container.repository().create_sample(sample)
    return sample


@app.post("/api/v1/datasets/{dataset_id}/samples/import", response_model=BulkCreateSampleResponse)
async def import_samples(
    dataset_id: str,
    payload: BulkCreateSampleRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> BulkCreateSampleResponse:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if not dataset.ls_project_id:
        raise HTTPException(status_code=500, detail="Dataset has no Label Studio project — cannot create sample.")
    if not payload.items:
        return BulkCreateSampleResponse(dataset_id=dataset_id, imported=0, failed=0)

    ls_tasks: list[dict] = []
    for item in payload.items:
        image_url = _make_ls_image_url(item.image_uris[0]) if item.image_uris else ""
        task_data = {"image": image_url}
        if dataset.task_spec.task_type == TaskType.VQA:
            task_data["question"] = str(item.metadata.get("question", ""))
        ls_tasks.append(task_data)

    try:
        imported = await container.label_studio_client().import_tasks(
            int(dataset.ls_project_id),
            ls_tasks,
            return_task_ids=True,
        )
        task_ids = [int(task_id) for task_id in imported.get("task_ids", [])]
        if len(task_ids) != len(payload.items):
            raise HTTPException(status_code=502, detail="Label Studio bulk import returned mismatched task IDs.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Label Studio bulk import failed: {exc}")

    samples = [
        Sample(
            dataset_id=dataset_id,
            image_uris=item.image_uris,
            metadata=item.metadata,
            ls_task_id=task_ids[idx],
        )
        for idx, item in enumerate(payload.items)
    ]
    created = await container.repository().create_samples(samples)

    for idx, item in enumerate(payload.items):
        if item.label is None:
            continue
        sample = created[idx]
        if sample.ls_task_id is not None:
            await container.label_studio_client().create_annotation(
                sample.ls_task_id,
                platform_annotation_to_ls(item.label),
            )
        await container.repository().create_annotation(
            Annotation(
                sample_id=sample.id,
                label=item.label,
                created_by=current_user.email,
            ),
            user_id=current_user.id,
        )

    return BulkCreateSampleResponse(
        dataset_id=dataset_id,
        imported=len(created),
        failed=0,
        sample_ids=[sample.id for sample in created],
        ls_task_ids=task_ids,
    )


@app.post("/api/v1/datasets/{dataset_id}/samples/import-vqa", response_model=ImportVqaJsonlResponse)
async def import_vqa_samples(
    dataset_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ImportVqaJsonlResponse:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if dataset.task_spec.task_type != TaskType.VQA:
        raise HTTPException(status_code=400, detail="dataset task_type must be 'vqa'")
    if not dataset.ls_project_id:
        raise HTTPException(status_code=500, detail="Dataset has no Label Studio project")
    content = (await file.read()).decode("utf-8")
    ls_client = container.label_studio_client()
    imported = 0
    failed = 0
    errors: list[str] = []

    for idx, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("line is not a JSON object")
            image_uri = str(row.get("image_uri", "")).strip()
            question = str(row.get("question", "")).strip()
            answer = row.get("answer")
            if not image_uri:
                raise ValueError("image_uri is required")
            if not question:
                raise ValueError("question is required")

            image_url = _make_ls_image_url(image_uri)
            task = await ls_client.create_task(
                int(dataset.ls_project_id),
                {"image": image_url, "question": question},
            )
            ls_task_id = task.get("id")
            if ls_task_id is None:
                raise ValueError("Label Studio task creation returned no ID")

            metadata = {"question": question}
            if answer is not None:
                metadata["answer"] = str(answer)

            sample = Sample(
                dataset_id=dataset_id,
                image_uris=[image_uri],
                metadata=metadata,
                ls_task_id=int(ls_task_id),
            )
            await container.repository().create_sample(sample)
            imported += 1
        except Exception as exc:
            failed += 1
            errors.append(f"line {idx}: {exc}")

    return ImportVqaJsonlResponse(
        dataset_id=dataset_id,
        imported=imported,
        failed=failed,
        errors=errors,
    )


@app.get("/api/v1/datasets/{dataset_id}/samples", response_model=PaginatedResponse[Sample])
async def list_samples(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PaginatedResponse[Sample]:
    items, total = await container.repository().list_samples(dataset_id, offset=offset, limit=limit)
    return PaginatedResponse(items=items, total=total)


@app.get("/api/v1/datasets/{dataset_id}/samples-with-labels", response_model=PaginatedResponse[SampleWithLabels])
async def list_samples_with_labels_endpoint(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    label: str | None = None,
    order_by: str = "id",
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PaginatedResponse[SampleWithLabels]:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    items, total = await container.repository().list_samples_with_labels(
        dataset_id=dataset_id,
        offset=offset,
        limit=limit,
        label_filter=label,
        order_by=order_by,
    )
    return PaginatedResponse(items=[SampleWithLabels(**item) for item in items], total=total)


@app.get("/api/v1/samples/{sample_id}", response_model=Sample)
async def get_sample(
    sample_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Sample:
    sample = await container.repository().get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    return sample


@app.post("/api/v1/samples/{sample_id}/embed")
async def embed_sample(
    sample_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    sample = await container.repository().get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    if not sample.image_uris:
        raise HTTPException(status_code=400, detail="no image")

    uri = sample.image_uris[0]
    if uri.startswith("data:"):
        try:
            _, encoded = uri.split(",", 1)
            image_bytes = base64.b64decode(encoded)
        except Exception:
            raise HTTPException(status_code=400, detail="malformed data URI")
    elif uri.startswith("s3://") or uri.startswith("memory://"):
        try:
            image_bytes = await container.artifact_storage().get_bytes(uri)
        except (FileNotFoundError, KeyError):
            raise HTTPException(status_code=404, detail="image not found")
    else:
        raise HTTPException(status_code=400, detail="unsupported URI scheme")

    dataset = await container.repository().get_dataset(sample.dataset_id)
    embed_model: str = (dataset.embed_config or {}).get("model", "openai/clip-vit-base-patch32") if dataset else "openai/clip-vit-base-patch32"
    embedding_svc = container.embedding_service()
    embedding = await embedding_svc.embed_image(image_bytes, model_name=embed_model)
    feature = await container.repository().upsert_sample_feature(sample_id, embedding, embed_model)
    return {
        "sample_id": feature.sample_id,
        "embed_model": feature.embed_model,
        "embedding_dim": len(feature.embedding),
    }


@app.post("/api/v1/annotations", response_model=Annotation)
async def create_annotation(
    payload: CreateAnnotationRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Annotation:
    sample = await container.repository().get_sample(payload.sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    if not sample.ls_task_id:
        raise HTTPException(status_code=500, detail="Sample has no Label Studio task — cannot create annotation.")
    # LS-first: sync annotation before persisting locally (avoid orphan rows on LS failure)
    try:
        from app.services.label_studio import platform_annotation_to_ls
        ls_result = platform_annotation_to_ls(payload.label)
        await container.label_studio_client().create_annotation(
            sample.ls_task_id, ls_result
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Label Studio annotation sync failed: {exc}")
    ann = Annotation(sample_id=payload.sample_id, label=payload.label, created_by=current_user.id)
    ann = await container.repository().create_annotation(ann)
    return ann


@app.get("/api/v1/samples/{sample_id}/annotations", response_model=list[Annotation])
async def list_annotations_for_sample(
    sample_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[Annotation]:
    if await container.repository().get_sample(sample_id) is None:
        raise HTTPException(status_code=404, detail="sample not found")
    return await container.repository().list_annotations_for_sample(sample_id)


@app.patch("/api/v1/annotations/{annotation_id}", response_model=Annotation)
async def update_annotation(
    annotation_id: str,
    payload: UpdateAnnotationRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Annotation:
    result = await container.repository().update_annotation(annotation_id, payload.label)
    if result is None:
        raise HTTPException(status_code=404, detail="annotation not found")
    return result


@app.delete("/api/v1/annotations/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    deleted = await container.repository().delete_annotation(annotation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="annotation not found")
    return Response(status_code=204)


@app.post("/api/v1/datasets/{dataset_id}/annotations/bulk")
async def bulk_create_annotations(
    dataset_id: str,
    payload: BulkAnnotationRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    created = 0
    for item in payload.annotations:
        ann = Annotation(
            id=__import__("uuid").uuid4().hex,
            sample_id=item.sample_id,
            label=item.label,
            created_by=current_user.id,
        )
        await container.repository().create_annotation(ann)
        created += 1
    return {"created": created}


@app.post("/api/v1/datasets/{dataset_id}/sync-annotations-to-ls")
async def sync_annotations_to_ls(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not dataset.ls_project_id:
        raise HTTPException(status_code=500, detail="Dataset has no Label Studio project — cannot sync annotations.")

    # Get all samples and annotations for this dataset
    samples, _ = await container.repository().list_samples(dataset_id, limit=100_000)
    sample_map = {s.id: s for s in samples}
    annotations = await container.repository().list_annotations_for_dataset(dataset_id)

    synced_count = 0
    errors = []
    ls_client = container.label_studio_client()

    from app.services.label_studio import platform_annotation_to_ls
    for ann in annotations:
        sample = sample_map.get(ann.sample_id)
        if not sample:
            errors.append(f"annotation {ann.id}: sample {ann.sample_id} not found")
            continue
        if not sample.ls_task_id:
            errors.append(f"annotation {ann.id}: sample {ann.sample_id} has no ls_task_id — cannot sync")
            continue
        try:
            ls_result = platform_annotation_to_ls(ann.label)
            await ls_client.create_annotation(sample.ls_task_id, ls_result)
            synced_count += 1
        except Exception as e:
            errors.append(f"annotation {ann.id}: {str(e)}")

    return {"synced_count": synced_count, "errors": errors}


@app.get("/api/v1/training-presets")
async def list_presets(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[dict]:
    registry = container.preset_registry()
    return [registry.preset_to_api_dict(p) for p in registry.list_presets()]


@app.get("/api/v1/training-presets/{preset_id}")
async def get_preset(
    preset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    registry = container.preset_registry()
    spec = registry.get_preset(preset_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return registry.preset_to_api_dict(spec)


@app.post("/api/v1/training-jobs", response_model=TrainingJob)
async def create_training_job(
    payload: CreateTrainingJobRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainingJob:
    dataset = await container.repository().get_dataset(payload.dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    registry = container.preset_registry()
    preset = registry.get_preset(payload.preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    if not preset.trainable:
        raise HTTPException(
            status_code=422,
            detail=(
                f"preset '{preset.id}' is inference-only and does not support training jobs"
            ),
        )
    try:
        validate_dataset_preset_training(dataset, preset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    job = TrainingJob(dataset_id=payload.dataset_id, preset_id=payload.preset_id, created_by=current_user.id, org_id=org.id)
    return await container.orchestrator().start_job(job)


@app.get("/api/v1/training-jobs", response_model=list[TrainingJob])
async def list_jobs(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[TrainingJob]:
    return await container.repository().list_jobs(org_id=org.id)


@app.get("/api/v1/training-jobs/{job_id}", response_model=TrainingJob)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainingJob:
    job = await container.repository().get_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/api/v1/training-jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict[str, bool]:
    ok = await container.orchestrator().cancel_job(job_id)
    return {"cancelled": ok}


@app.get("/api/v1/task-tracker/tasks", response_model=list[TaskTrackerSummaryResponse])
async def list_task_tracker_tasks(
    kind: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[TaskTrackerSummaryResponse]:
    if kind not in (None, "training", "prediction", "schedule_run"):
        raise HTTPException(status_code=422, detail="invalid task kind")
    return await container.task_tracker().list_tasks(org_id=org.id, kind=kind)


@app.get("/api/v1/task-tracker/tasks/{task_id}", response_model=TaskTrackerDetailResponse)
async def get_task_tracker_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TaskTrackerDetailResponse:
    detail = await container.task_tracker().get_task(task_id, org_id=org.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="task not found")
    return detail


@app.post("/api/v1/task-tracker/tasks/{task_id}/cancel")
async def cancel_task_tracker_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict[str, bool]:
    ok = await container.task_tracker().cancel_task(task_id, org_id=org.id)
    if not ok:
        raise HTTPException(status_code=404, detail="task not found or not cancellable")
    return {"cancelled": True}


@app.get("/api/v1/task-tracker/tasks/{task_id}/stream")
async def stream_task_tracker_task(
    task_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    if await container.task_tracker().get_task(task_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="task not found")

    async def event_stream():
        last_payload = ""
        while True:
            if await request.is_disconnected():
                break
            detail = await container.task_tracker().get_task(task_id, org_id=org.id)
            if detail is None:
                break
            payload = json.dumps(detail.model_dump(mode="json"))
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
            status = detail.derived.display_status
            if status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/v1/training-jobs/{job_id}/events")
async def get_job_events(
    job_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    if await container.repository().get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_stream():
        idx = 0
        while True:
            if await request.is_disconnected():
                break
            events = await container.repository().list_events(job_id)
            while idx < len(events):
                line = f"data: {json.dumps(events[idx].model_dump(mode='json'))}\n\n"
                yield line
                idx += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/v1/training-jobs/{job_id}/events/history", response_model=PaginatedResponse[TrainingEvent])
async def get_job_events_history(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PaginatedResponse[TrainingEvent]:
    if await container.repository().get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    items, total = await container.repository().list_events_paginated(job_id, offset=offset, limit=limit)
    return PaginatedResponse(items=items, total=total)


@app.post("/api/v1/training-jobs/{job_id}/mark-left")
async def mark_user_left(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict[str, bool]:
    if await container.repository().get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"marked": await container.repository().mark_user_left(job_id)}


async def _build_export_data(dataset_id: str):
    """Return (dataset, samples, annotations) — sourcing from LS Postgres directly.

    LS is always required. The dataset must have an ``ls_project_id``.
    Annotations are read from LS's ``task_completion`` table via ``LsReadRepository``.
    Raises 500 if no LS project, 502 if LS DB read fails. NO local fallback.
    """
    from app.services.label_studio import ls_annotation_to_platform

    repo = container.repository()
    dataset = await repo.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")

    if not dataset.ls_project_id:
        raise HTTPException(status_code=500, detail="Dataset has no Label Studio project — cannot export.")

    try:
        ls_read = container.ls_read_repository()

        # Get all platform samples for this dataset
        all_samples, _ = await repo.list_samples(dataset_id, limit=100_000)
        task_id_to_sample: dict[int, Sample] = {
            s.ls_task_id: s for s in all_samples if s.ls_task_id is not None
        }

        # Read tasks and annotations from LS Postgres
        ls_tasks = await ls_read.get_tasks_for_project(int(dataset.ls_project_id))
        task_ids = [t["id"] for t in ls_tasks]
        ls_annotations = await ls_read.get_annotations_for_tasks(task_ids) if task_ids else {}

        samples_out: list[Sample] = []
        annotations_out: list[Annotation] = []

        for ls_task in ls_tasks:
            task_id = ls_task["id"]
            platform_sample = task_id_to_sample.get(task_id)
            if platform_sample is None:
                continue
            samples_out.append(platform_sample)

            for ls_ann in ls_annotations.get(task_id, []):
                result = ls_ann.get("result", [])
                label = ls_annotation_to_platform(result)
                if label:
                    annotations_out.append(
                        Annotation(
                            sample_id=platform_sample.id,
                            label=label,
                            created_by="label_studio",
                        )
                    )

        return dataset, samples_out, annotations_out

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Label Studio database read failed: {exc}")


@app.get("/api/v1/exports/{dataset_id}")
async def export_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    dataset, samples, anns = await _build_export_data(dataset_id)
    return container.artifacts().build_dataset_export(
        dataset=dataset,
        samples=samples,
        annotations=anns,
    )


@app.post("/api/v1/exports/{dataset_id}/persist")
async def export_dataset_persist(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    dataset, samples, anns = await _build_export_data(dataset_id)
    uri = await container.artifacts().persist_dataset_export(dataset=dataset, samples=samples, annotations=anns)
    return {"uri": uri}


@app.post("/api/v1/datasets/{dataset_id}/features/extract")
async def extract_features(
    dataset_id: str,
    force: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")

    embed_model: str = (dataset.embed_config or {}).get("model", "openai/clip-vit-base-patch32")
    from app.domain.models import PredictionJob
    job = PredictionJob(
        dataset_id=dataset_id,
        model_id="embedding-worker",
        created_by=current_user.id,
        target="embedding",
        org_id=org.id,
        model_version="force" if force else None,
        summary={"embed_model": embed_model},
    )
    if str(container.config().app.env) == "test":
        from app.domain.types import JobStatus

        samples, total = await container.repository().list_samples(dataset_id, limit=100_000)
        result = await container.feature_ops().extract_features(
            samples=samples,
            embed_model=embed_model,
            force=force,
            storage=container.artifact_storage(),
        )
        job.status = JobStatus.COMPLETED
        job.summary = {
            "status": result.get("status", "completed"),
            "total_samples": total,
            "processed": result.get("computed", 0),
            "skipped": result.get("skipped", 0),
            "embedding_model": result.get("embedding_model", embed_model),
        }
        persisted = await container.repository().create_prediction_job(job, org_id=org.id)
        return _prediction_job_to_response(persisted).model_dump()
    started = await container.prediction_orchestrator().start_job(job)
    return _prediction_job_to_response(started).model_dump()


@app.get("/api/v1/datasets/{dataset_id}/similarity/{sample_id}")
async def similarity_search(
    dataset_id: str,
    sample_id: str,
    k: int = 5,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    if await container.repository().get_dataset(dataset_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    sample = await container.repository().get_sample(sample_id)
    if sample is None or sample.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="sample not found")
    return await container.feature_ops().similarity_search(sample_id, dataset_id=dataset_id, k=k)


@app.get("/api/v1/datasets/{dataset_id}/selection-metrics")
async def selection_metrics(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    if await container.repository().get_dataset(dataset_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    samples, _ = await container.repository().list_samples(dataset_id, limit=100_000)
    sample_ids = [s.id for s in samples]
    fs = container.feature_ops()
    return {
        "uniqueness": await fs.uniqueness_scores(sample_ids, dataset_id=dataset_id),
        "representativeness": await fs.representativeness_scores(sample_ids, dataset_id=dataset_id),
    }


@app.get("/api/v1/datasets/{dataset_id}/hints/uncovered")
async def uncovered_hints(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    if await container.repository().get_dataset(dataset_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return await container.feature_ops().uncovered_cluster_hints(dataset_id)


@app.get("/api/v1/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    artifact = await container.repository().get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        data = await container.artifact_storage().get_bytes(artifact.uri)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="artifact data not found")
    return Response(content=data, media_type="application/octet-stream")


# ---------------------------------------------------------------------------
# Model management endpoints
# ---------------------------------------------------------------------------


def _model_to_response(model) -> ModelResponse:
    """Convert domain Model to API response."""
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


@app.get("/api/v1/models", response_model=list[ModelResponse])
async def list_models(
    dataset_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[ModelResponse]:
    """List all trained models, optionally filtered by dataset or job."""
    models = await container.model_service().list_models(
        org_id=org.id,
        dataset_id=dataset_id,
        job_id=job_id,
    )
    return [_model_to_response(m) for m in models]


@app.get("/api/v1/models/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ModelResponse:
    """Get a single model by ID."""
    model = await container.model_service().get_model(model_id, org_id=org.id)
    return _model_to_response(model)


@app.delete("/api/v1/models/{model_id}", status_code=204)
async def delete_model(
    model_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    """Delete a model artifact."""
    await container.model_service().delete_model(model_id, org_id=org.id)
    return Response(status_code=204)


@app.get("/api/v1/models/{model_id}/download")
async def download_model(
    model_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    """Download a model file."""
    data, filename = await container.model_service().download_model(model_id, org_id=org.id)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/v1/model-upload-templates", response_model=list[ModelUploadTemplateResponse])
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
                    model_spec=profile.get("model_spec", {}) if isinstance(profile.get("model_spec", {}), dict) else {},
                    default_prediction_targets=profile.get("default_prediction_targets", []),
                )
                for profile in template.profiles
            ],
        )
        for template in UPLOAD_TEMPLATE_DEFINITIONS
    ]


@app.post("/api/v1/models/upload", response_model=ModelResponse)
async def upload_model(
    file: UploadFile = File(...),
    metadata: str = Form(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ModelResponse:
    """Upload an external model file and associate it with a training job."""
    model = await container.model_service().upload_model(
        file=file,
        org_id=org.id,
        metadata_json=metadata,
    )
    return _model_to_response(model)


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@app.post("/api/v1/samples/{sample_id}/upload", response_model=UpdateSampleImageResponse)
async def upload_sample_image(
    sample_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> UpdateSampleImageResponse:
    sample = await container.repository().get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="file must be an image")
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 10 MB limit")
    key = f"samples/{sample_id}/{file.filename}"
    uri = await container.artifact_storage().put_bytes(key, data, file.content_type or "application/octet-stream")
    existing_uris = list(sample.image_uris or [])
    index = len(existing_uris)
    updated_uris = existing_uris + [uri]
    await container.repository().update_sample_image_uris(sample_id, updated_uris)
    return UpdateSampleImageResponse(uri=uri, sample_id=sample_id, index=index)


@app.get("/api/v1/images/resolve")
async def resolve_image(uri: str = Query(...)) -> Response:
    if uri.startswith("http://") or uri.startswith("https://"):
        cfg = container.config()
        ls_url = str(cfg.label_studio.url).rstrip("/")
        if not (ls_url and uri.startswith(ls_url)):
            raise HTTPException(status_code=400, detail="http/https URIs are not allowed")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(uri)
                resp.raise_for_status()
        except Exception:
            raise HTTPException(status_code=502, detail="failed to fetch image from Label Studio")
        content_type = resp.headers.get("content-type") or resp.headers.get("Content-Type")
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
            mime_part = header.split(";")[0][len("data:"):]
            data = base64.b64decode(encoded)
            return Response(content=data, media_type=mime_part or "application/octet-stream")
        except Exception:
            raise HTTPException(status_code=400, detail="malformed data URI")
    # Handle storage URIs (s3:// or memory://)
    if uri.startswith("s3://") or uri.startswith("memory://"):
        try:
            data = await container.artifact_storage().get_bytes(uri)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="image not found")
        # Attempt to infer content type from URI extension
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


# ---------------------------------------------------------------------------
# Embed config endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/datasets/{dataset_id}/embed-config")
async def get_embed_config(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return dataset.embed_config or {}


@app.patch("/api/v1/datasets/{dataset_id}/embed-config")
async def update_embed_config(
    dataset_id: str,
    payload: UpdateEmbedConfigRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    new_config = {"model": payload.model, "dimension": payload.dimension}
    await container.repository().update_dataset_embed_config(dataset_id, new_config)
    return new_config


# ---------------------------------------------------------------------------
# Prediction endpoints
# ---------------------------------------------------------------------------


def _prediction_result_to_response(result) -> PredictionResultResponse:
    """Convert domain PredictionResult to API response."""
    return PredictionResultResponse(
        sample_id=result.sample_id,
        ls_task_id=result.ls_task_id,
        predicted_label=result.predicted_label,
        confidence=result.confidence,
        ls_prediction_id=result.ls_prediction_id,
        error=result.error,
    )


def _prediction_job_to_response(job) -> PredictionJobResponse:
    status = job.status.value if hasattr(job.status, "value") else str(job.status)
    return PredictionJobResponse(
        id=job.id,
        dataset_id=job.dataset_id,
        model_id=job.model_id,
        status=status,
        created_by=job.created_by,
        target=job.target,
        model_version=job.model_version,
        created_at=job.created_at,
        updated_at=job.updated_at,
        external_job_id=job.external_job_id,
        sample_ids=job.sample_ids,
        summary=job.summary,
    )


@app.post("/api/v1/predictions/run", response_model=PredictionJobResponse, status_code=202)
async def run_predictions(
    payload: RunPredictionRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PredictionJobResponse:
    """Create an async prediction job for dataset-scale inference."""
    try:
        from app.domain.models import PredictionJob

        job = PredictionJob(
            dataset_id=payload.dataset_id,
            model_id=payload.model_id,
            created_by=current_user.id,
            target=payload.target,
            model_version=payload.model_version,
            org_id=org.id,
            sample_ids=payload.sample_ids,
        )
        if str(container.config().app.env) == "test":
            from app.domain.models import PredictionEvent
            from app.domain.types import JobStatus

            result = await container.prediction_service().run_prediction(
                model_id=payload.model_id,
                dataset_id=payload.dataset_id,
                org_id=org.id,
                sample_ids=payload.sample_ids,
                model_version=payload.model_version,
                target=payload.target,
                prompt=payload.prompt,
            )
            job.status = JobStatus.COMPLETED
            job.summary = result.model_dump(mode="json")
            persisted = await container.repository().create_prediction_job(job, org_id=org.id)
            await container.repository().add_prediction_event(
                PredictionEvent(
                    job_id=persisted.id,
                    message="prediction completed in test mode",
                    payload={"summary": persisted.summary},
                )
            )
            return _prediction_job_to_response(persisted)
        started = await container.prediction_orchestrator().start_job(job)
        return _prediction_job_to_response(started)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/prediction-jobs", response_model=list[PredictionJobResponse])
async def list_prediction_jobs(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[PredictionJobResponse]:
    jobs = await container.repository().list_prediction_jobs(org_id=org.id)
    return [_prediction_job_to_response(job) for job in jobs]


@app.get("/api/v1/prediction-jobs/{job_id}", response_model=PredictionJobResponse)
async def get_prediction_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PredictionJobResponse:
    job = await container.repository().get_prediction_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Prediction job not found")
    return _prediction_job_to_response(job)


@app.get("/api/v1/prediction-jobs/{job_id}/events", response_model=list[PredictionEventResponse])
async def list_prediction_job_events(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[PredictionEventResponse]:
    job = await container.repository().get_prediction_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Prediction job not found")
    events = await container.repository().list_prediction_events(job_id)
    return [PredictionEventResponse(job_id=e.job_id, ts=e.ts, level=e.level, message=e.message, payload=e.payload) for e in events]


@app.post("/api/v1/prediction-jobs/{job_id}/cancel")
async def cancel_prediction_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    cancelled = await container.prediction_orchestrator().cancel_job(job_id, org_id=org.id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Prediction job not found or not cancellable")
    return {"cancelled": True}


@app.post("/api/v1/predictions/single", response_model=PredictionResultResponse)
async def predict_single(
    payload: PredictSingleRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PredictionResultResponse:
    """Run prediction on a single sample using a trained model."""
    try:
        result = await container.prediction_service().predict_single(
            model_id=payload.model_id,
            sample_id=payload.sample_id,
            org_id=org.id,
            model_version=payload.model_version,
            target=payload.target,
            prompt=payload.prompt,
        )
        return _prediction_result_to_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/samples/{sample_id}/predictions")
async def list_sample_predictions(
    sample_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[dict]:
    """List all predictions for a sample from Label Studio."""
    try:
        return await container.prediction_service().list_predictions_for_sample(
            sample_id=sample_id,
            org_id=org.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Prediction review endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/prediction-reviews", response_model=ReviewActionResponse, status_code=201)
async def create_review_action(
    payload: CreateReviewActionRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ReviewActionResponse:
    """Create a new prediction review session."""
    try:
        action = await container.prediction_service().create_review_action(
            dataset_id=payload.dataset_id,
            model_id=payload.model_id,
            org_id=org.id,
            created_by=current_user.id,
            model_version=payload.model_version,
        )
        return ReviewActionResponse(
            id=action.id,
            dataset_id=action.dataset_id,
            model_id=action.model_id,
            model_version=action.model_version,
            created_by=action.created_by,
            created_at=action.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/prediction-reviews", response_model=list[ReviewActionResponse])
async def list_review_actions(
    dataset_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[ReviewActionResponse]:
    """List all prediction review actions for a dataset."""
    actions = await container.repository().list_review_actions(dataset_id)
    return [
        ReviewActionResponse(
            id=a.id,
            dataset_id=a.dataset_id,
            model_id=a.model_id,
            model_version=a.model_version,
            created_by=a.created_by,
            created_at=a.created_at,
        )
        for a in actions
    ]


@app.get("/api/v1/prediction-reviews/{action_id}", response_model=ReviewActionResponse)
async def get_review_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ReviewActionResponse:
    """Get a single prediction review action."""
    action = await container.repository().get_review_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")
    return ReviewActionResponse(
        id=action.id,
        dataset_id=action.dataset_id,
        model_id=action.model_id,
        model_version=action.model_version,
        created_by=action.created_by,
        created_at=action.created_at,
    )


@app.delete("/api/v1/prediction-reviews/{action_id}", status_code=204)
async def delete_review_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    """Delete a prediction review action and its annotation versions."""
    deleted = await container.repository().delete_review_action(action_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Review action not found")
    return Response(status_code=204)


@app.post(
    "/api/v1/prediction-reviews/{action_id}/annotations",
    response_model=SaveReviewAnnotationsResponse,
)
async def save_review_annotations(
    action_id: str,
    payload: SaveReviewAnnotationsRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SaveReviewAnnotationsResponse:
    """Save reviewed predictions as annotations for a review action."""
    try:
        items = [item.model_dump() for item in payload.items]
        _annotations, versions = await container.prediction_service().save_review_annotations(
            review_action_id=action_id,
            items=items,
            created_by=current_user.id,
        )
        return SaveReviewAnnotationsResponse(
            review_action_id=action_id,
            created_count=len(versions),
            annotation_versions=[
                AnnotationVersionResponse(
                    id=v.id,
                    review_action_id=v.review_action_id,
                    annotation_id=v.annotation_id,
                    source_prediction_id=v.source_prediction_id,
                    predicted_label=v.predicted_label,
                    final_label=v.final_label,
                    confidence=v.confidence,
                    created_at=v.created_at,
                )
                for v in versions
            ],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get(
    "/api/v1/prediction-reviews/{action_id}/annotation-versions",
    response_model=list[AnnotationVersionResponse],
)
async def list_annotation_versions(
    action_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[AnnotationVersionResponse]:
    """List annotation versions for a review action."""
    action = await container.repository().get_review_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")
    versions = await container.repository().list_annotation_versions(action_id)
    return [
        AnnotationVersionResponse(
            id=v.id,
            review_action_id=v.review_action_id,
            annotation_id=v.annotation_id,
            source_prediction_id=v.source_prediction_id,
            predicted_label=v.predicted_label,
            final_label=v.final_label,
            confidence=v.confidence,
            created_at=v.created_at,
        )
        for v in versions
    ]


@app.get("/api/v1/export-formats", response_model=list[ExportFormatResponse])
async def list_export_formats(
    current_user: User = Depends(get_current_user),
) -> list[ExportFormatResponse]:
    """List all available annotation-version export formats."""
    from app.services.artifacts import list_export_formats as _list_fmts
    return [ExportFormatResponse(format_id=f["format_id"]) for f in _list_fmts()]


@app.get("/api/v1/prediction-reviews/{action_id}/export")
async def export_review_version(
    action_id: str,
    format_id: str = Query(default="annotation-version-full-context-v1"),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    """Preview (return JSON) an annotation-version export."""
    from app.services.artifacts import get_export_builder

    action = await container.repository().get_review_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")

    try:
        builder = get_export_builder(format_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown export format: {format_id}")

    repo = container.repository()
    dataset = await repo.get_dataset(action.dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    versions = await repo.list_annotation_versions(action_id)
    # Collect touched annotation IDs → fetch annotations → fetch samples
    ann_ids = [v.annotation_id for v in versions]
    annotations = []
    sample_ids_set: set[str] = set()
    for aid in ann_ids:
        ann = await repo.get_annotation(aid)
        if ann is not None:
            annotations.append(ann)
            sample_ids_set.add(ann.sample_id)

    samples = []
    for sid in sample_ids_set:
        s = await repo.get_sample(sid)
        if s is not None:
            samples.append(s)

    return builder(
        review_action=action,
        dataset=dataset,
        samples=samples,
        annotations=annotations,
        versions=versions,
    )


@app.post("/api/v1/prediction-reviews/{action_id}/export/persist")
async def persist_review_export(
    action_id: str,
    payload: VersionExportRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    """Persist an annotation-version export to artifact storage."""
    action = await container.repository().get_review_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")

    repo = container.repository()
    dataset = await repo.get_dataset(action.dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    versions = await repo.list_annotation_versions(action_id)
    ann_ids = [v.annotation_id for v in versions]
    annotations = []
    sample_ids_set: set[str] = set()
    for aid in ann_ids:
        ann = await repo.get_annotation(aid)
        if ann is not None:
            annotations.append(ann)
            sample_ids_set.add(ann.sample_id)

    samples = []
    for sid in sample_ids_set:
        s = await repo.get_sample(sid)
        if s is not None:
            samples.append(s)

    try:
        uri = await container.artifacts().persist_version_export(
            review_action=action,
            dataset=dataset,
            samples=samples,
            annotations=annotations,
            versions=versions,
            format_id=payload.format_id,
        )
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown export format: {payload.format_id}")

    return {"uri": uri, "format_id": payload.format_id}


@app.patch("/api/v1/datasets/{dataset_id}/public")
async def set_dataset_public(
    dataset_id: str,
    payload: SetPublicRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    await require_superadmin(current_user=current_user)
    ok = await container.repository().set_dataset_public(dataset_id, payload.is_public)
    if not ok:
        raise HTTPException(status_code=404, detail="dataset not found")
    return {"ok": True}


@app.patch("/api/v1/training-jobs/{job_id}/public")
async def set_job_public(
    job_id: str,
    payload: SetPublicRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    await require_superadmin(current_user=current_user)
    ok = await container.repository().set_job_public(job_id, payload.is_public)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/auth/register", response_model=UserResponse, status_code=201)
async def register(payload: RegisterRequest) -> UserResponse:
    repo = container.repository()
    existing = await repo.get_user_by_email(payload.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    hashed = hash_password(payload.password)
    user_orm = UserORM(
        email=payload.email,
        name=payload.name,
        hashed_password=hashed,
    )
    user_orm = await repo.create_user(user_orm)
    return UserResponse(
        id=user_orm.id,
        email=user_orm.email,
        name=user_orm.name,
        is_superadmin=user_orm.is_superadmin,
        created_at=user_orm.created_at,
    )


@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    repo = container.repository()
    user_orm = await repo.get_user_by_email(payload.email)
    if user_orm is None or not user_orm.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, user_orm.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user_orm.id})
    user_resp = UserResponse(
        id=user_orm.id,
        email=user_orm.email,
        name=user_orm.name,
        is_superadmin=user_orm.is_superadmin,
        created_at=user_orm.created_at,
    )
    return LoginResponse(access_token=token, user=user_resp)


@app.get("/api/v1/auth/me", response_model=UserWithOrgsResponse)
async def auth_me(current_user: User = Depends(get_current_user)) -> UserWithOrgsResponse:
    repo = container.repository()
    memberships = await repo.get_user_orgs(current_user.id)
    orgs = [
        MembershipResponse(
            org_id=org.id,
            org_name=org.name,
            org_slug=org.slug,
            role=membership.role,
        )
        for membership, org in memberships
    ]
    return UserWithOrgsResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        is_superadmin=current_user.is_superadmin,
        created_at=current_user.created_at,
        organizations=orgs,
    )


# ---------------------------------------------------------------------------
# PAT endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/auth/tokens", response_model=TokenCreatedResponse, status_code=201)
async def create_token(
    payload: CreateTokenRequest,
    current_user: User = Depends(get_current_user),
) -> TokenCreatedResponse:
    plaintext, pat_orm = create_personal_access_token(current_user.id, payload.name)
    repo = container.repository()
    pat_orm = await repo.create_pat(pat_orm)
    return TokenCreatedResponse(
        id=pat_orm.id,
        name=pat_orm.name,
        token=plaintext,
        created_at=pat_orm.created_at,
    )


@app.get("/api/v1/auth/tokens", response_model=list[TokenResponse])
async def list_tokens(
    current_user: User = Depends(get_current_user),
) -> list[TokenResponse]:
    repo = container.repository()
    pats = await repo.list_personal_access_tokens(current_user.id)
    return [
        TokenResponse(
            id=pat.id,
            name=pat.name,
            token_prefix=pat.token_prefix,
            created_at=pat.created_at,
        )
        for pat in pats
    ]


@app.delete("/api/v1/auth/tokens/{token_id}", status_code=204)
async def delete_token(
    token_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    repo = container.repository()
    deleted = await repo.delete_personal_access_token(token_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Token not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Org management endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/organizations", response_model=OrgResponse, status_code=201)
async def create_organization(
    payload: CreateOrgRequest,
    current_user: User = Depends(get_current_user),
) -> OrgResponse:
    await require_superadmin(current_user=current_user)
    repo = container.repository()
    slug = payload.slug if payload.slug else payload.name.lower().replace(" ", "-")
    existing = await repo.get_organization_by_slug(slug)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Organization slug already exists")
    org_orm = OrganizationORM(name=payload.name, slug=slug)
    org_orm = await repo.create_organization(org_orm)
    membership = OrgMembershipORM(user_id=current_user.id, org_id=org_orm.id, role="admin")
    await repo.add_org_member(membership)
    return OrgResponse(
        id=org_orm.id,
        name=org_orm.name,
        slug=org_orm.slug,
        created_at=org_orm.created_at,
    )


@app.get("/api/v1/organizations", response_model=list[OrgResponse])
async def list_organizations(
    current_user: User = Depends(get_current_user),
) -> list[OrgResponse]:
    repo = container.repository()
    if current_user.is_superadmin:
        orgs = await repo.list_all_organizations()
        return [OrgResponse(id=o.id, name=o.name, slug=o.slug, created_at=o.created_at) for o in orgs]
    memberships = await repo.get_user_orgs(current_user.id)
    return [
        OrgResponse(id=org.id, name=org.name, slug=org.slug, created_at=org.created_at)
        for _, org in memberships
    ]


@app.post("/api/v1/organizations/{org_id}/members", response_model=MemberResponse, status_code=201)
async def add_org_member(
    org_id: str,
    payload: AddMemberRequest,
    current_user: User = Depends(get_current_user),
) -> MemberResponse:
    repo = container.repository()
    org = await repo.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not current_user.is_superadmin:
        caller_membership = await repo.get_org_membership(org_id, current_user.id)
        if caller_membership is None or caller_membership.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    target_user = await repo.get_user(payload.user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    existing_membership = await repo.get_org_membership(org_id, payload.user_id)
    if existing_membership is not None:
        raise HTTPException(status_code=409, detail="User is already a member")
    membership = OrgMembershipORM(user_id=payload.user_id, org_id=org_id, role=payload.role)
    membership = await repo.add_org_member(membership)
    return MemberResponse(
        id=membership.id,
        user_id=target_user.id,
        user_email=target_user.email,
        user_name=target_user.name,
        role=membership.role,
        created_at=membership.created_at,
    )


@app.get("/api/v1/organizations/{org_id}/members", response_model=list[MemberResponse])
async def list_org_members(
    org_id: str,
    current_user: User = Depends(get_current_user),
) -> list[MemberResponse]:
    repo = container.repository()
    org = await repo.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not current_user.is_superadmin:
        caller_membership = await repo.get_org_membership(org_id, current_user.id)
        if caller_membership is None or caller_membership.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    members = await repo.get_org_members(org_id)
    return [
        MemberResponse(
            id=membership.id,
            user_id=user.id,
            user_email=user.email,
            user_name=user.name,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership, user in members
    ]


@app.delete("/api/v1/organizations/{org_id}/members/{user_id}", status_code=204)
async def remove_org_member(
    org_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    repo = container.repository()
    org = await repo.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not current_user.is_superadmin:
        caller_membership = await repo.get_org_membership(org_id, current_user.id)
        if caller_membership is None or caller_membership.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    removed = await repo.remove_org_member(org_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Dashboard endpoint
# ---------------------------------------------------------------------------


@app.get("/api/v1/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> DashboardResponse:
    """Return runtime analytics: work pool status, job queue stats, recent jobs."""
    repo = container.repository()
    cfg = container.config()
    service_health = container.service_health()

    # -- Job queue stats from local DB (scoped by org) --
    all_jobs = await repo.list_jobs(org_id=org.id)
    stats = JobQueueStats()
    for j in all_jobs:
        s = j.status.value if hasattr(j.status, "value") else str(j.status)
        if s == "queued":
            stats.queued += 1
        elif s == "running":
            stats.running += 1
        elif s == "completed":
            stats.completed += 1
        elif s == "failed":
            stats.failed += 1
        elif s == "cancelled":
            stats.cancelled += 1

    # -- Recent jobs (last 20) --
    sorted_jobs = sorted(all_jobs, key=lambda j: j.created_at, reverse=True)[:20]
    recent: list[RecentJobSummary] = [
        RecentJobSummary(
            id=j.id,
            dataset_id=j.dataset_id,
            preset_id=j.preset_id,
            status=j.status.value if hasattr(j.status, "value") else str(j.status),
            created_by=j.created_by,
            created_at=j.created_at if isinstance(j.created_at, str) else j.created_at.isoformat(),
            updated_at=j.updated_at if isinstance(j.updated_at, str) else j.updated_at.isoformat(),
        )
        for j in sorted_jobs
    ]

    # -- Work pool status from Prefect (only when engine is prefect) --
    work_pool: WorkPoolStatus | None = None
    prefect_connected = False
    engine_name = str(cfg.execution.engine)

    if engine_name == "prefect":
        pool_name = str(cfg.prefect.work_pool_name)
        try:
            prefect_client = container.prefect_client()
            pool_data = await prefect_client.get_work_pool(pool_name)
            prefect_connected = True

            # Count running flow runs to determine slots_used
            slots_used = 0
            try:
                running_runs = await prefect_client.filter_flow_runs(
                    work_pool_name=pool_name,
                    state_types=["RUNNING"],
                )
                slots_used = len(running_runs)
            except Exception:
                pass

            work_pool = WorkPoolStatus(
                name=pool_data.get("name", pool_name),
                type=pool_data.get("type", "unknown"),
                is_paused=pool_data.get("is_paused", False),
                concurrency_limit=pool_data.get("concurrency_limit"),
                slots_used=slots_used,
                status="paused" if pool_data.get("is_paused", False) else "ready",
            )
        except Exception:
            # Prefect not reachable — return dashboard without pool info
            pass

    services = [ServiceStatus.model_validate(item.model_dump()) for item in await service_health.check_all()]

    return DashboardResponse(
        work_pool=work_pool,
        job_queue=stats,
        recent_jobs=recent,
        services=services,
        prefect_connected=prefect_connected,
    )


# ---------------------------------------------------------------------------
# Schedule endpoints (Prefect-backed)
# ---------------------------------------------------------------------------


def _deployment_to_schedule(raw: dict) -> ScheduleResponse:
    # Handle ORM-based dict (from local DB path): has direct 'cron' and 'is_schedule_active'
    if "is_schedule_active" in raw and "prefect_deployment_id" in raw:
        return ScheduleResponse(
            id=raw.get("id", ""),
            name=raw.get("name", ""),
            flow_name=raw.get("flow_name", ""),
            cron=raw.get("cron"),
            parameters=raw.get("parameters", {}),
            description=raw.get("description", ""),
            is_schedule_active=raw.get("is_schedule_active", True),
            created=raw.get("created"),
            updated=raw.get("updated"),
            prefect_deployment_id=raw.get("prefect_deployment_id") or raw.get("id", ""),
        )
    # Handle Prefect deployment dict (legacy / mock path)
    schedules = raw.get("schedules", [])
    cron: str | None = None
    if schedules:
        cron = schedules[0].get("schedule", {}).get("cron")
    # Prefect 3.x uses "paused" (inverted logic vs our is_schedule_active)
    is_active = not raw.get("paused", False)
    return ScheduleResponse(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        flow_name=raw.get("flow_name", ""),
        cron=cron,
        parameters=raw.get("parameters", {}),
        description=raw.get("description", ""),
        is_schedule_active=is_active,
        created=raw.get("created"),
        updated=raw.get("updated"),
        prefect_deployment_id=raw.get("prefect_deployment_id") or raw.get("id", ""),
    )


def _run_to_response(raw: dict) -> RunResponse:
    return RunResponse(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        deployment_id=raw.get("deployment_id"),
        flow_name=raw.get("flow_name"),
        state_type=raw.get("state_type"),
        state_name=raw.get("state_name"),
        start_time=raw.get("start_time"),
        end_time=raw.get("end_time"),
        total_run_time=raw.get("total_run_time"),
        parameters=raw.get("parameters", {}),
    )


def _log_to_response(raw: dict) -> RunLogResponse:
    return RunLogResponse(
        id=raw.get("id"),
        flow_run_id=raw.get("flow_run_id"),
        level=raw.get("level", 0),
        timestamp=raw.get("timestamp", ""),
        message=raw.get("message", ""),
    )


@app.post("/api/v1/schedules", response_model=ScheduleResponse)
async def create_schedule(
    payload: CreateScheduleRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleResponse:
    raw = await svc.create_schedule(
        org_id=org.id,
        created_by=current_user.id,
        name=payload.name,
        flow_name=payload.flow_name,
        cron=payload.cron,
        parameters=payload.parameters,
        description=payload.description,
    )
    return _deployment_to_schedule(raw)


@app.get("/api/v1/schedules", response_model=list[ScheduleResponse])
async def list_schedules(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> list[ScheduleResponse]:
    raws = await svc.list_schedules(org_id=org.id)
    return [_deployment_to_schedule(r) for r in raws]


@app.get("/api/v1/schedules/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleResponse:
    raw = await svc.get_schedule(schedule_id, org_id=org.id)
    return _deployment_to_schedule(raw)


@app.patch("/api/v1/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    payload: UpdateScheduleRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleResponse:
    updates = payload.model_dump(exclude_none=True)
    # Translate our API fields to Prefect 3.x deployment fields
    prefect_updates: dict = {}
    if "name" in updates:
        prefect_updates["name"] = updates["name"]
    if "description" in updates:
        prefect_updates["description"] = updates["description"]
    if "parameters" in updates:
        prefect_updates["parameters"] = updates["parameters"]
    if "is_schedule_active" in updates:
        prefect_updates["paused"] = not updates["is_schedule_active"]
    if "cron" in updates:
        prefect_updates["schedules"] = [
            {
                "schedule": {"cron": updates["cron"], "timezone": "UTC"},
                "active": True,
            }
        ]
    raw = await svc.update_schedule(schedule_id, prefect_updates)
    return _deployment_to_schedule(raw)


@app.delete("/api/v1/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> Response:
    await svc.delete_schedule(schedule_id)
    return Response(status_code=204)


@app.post("/api/v1/schedules/{schedule_id}/run", response_model=RunResponse)
async def trigger_run(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> RunResponse:
    raw = await svc.trigger_run(schedule_id)
    return _run_to_response(raw)


@app.post("/api/v1/schedules/{schedule_id}/pause", response_model=ScheduleResponse)
async def pause_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleResponse:
    raw = await svc.pause_schedule(schedule_id)
    return _deployment_to_schedule(raw)


@app.post("/api/v1/schedules/{schedule_id}/resume", response_model=ScheduleResponse)
async def resume_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleResponse:
    raw = await svc.resume_schedule(schedule_id)
    return _deployment_to_schedule(raw)


@app.get("/api/v1/schedules/{schedule_id}/runs", response_model=list[RunResponse])
async def list_runs(
    schedule_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> list[RunResponse]:
    raws = await svc.list_runs(schedule_id, limit=limit)
    return [_run_to_response(r) for r in raws]


@app.get("/api/v1/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> RunResponse:
    raw = await svc.get_run(run_id)
    return _run_to_response(raw)


@app.get("/api/v1/runs/{run_id}/logs", response_model=list[RunLogResponse])
async def get_run_logs(
    run_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> list[RunLogResponse]:
    raws = await svc.get_run_logs(run_id, limit=limit)
    return [_log_to_response(r) for r in raws]
