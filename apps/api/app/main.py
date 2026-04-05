from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import json
import logging

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from app.api.schemas import (
    AddMemberRequest,
    BulkAnnotationRequest,
    CreateAnnotationRequest,
    CreateDatasetRequest,
    CreateOrgRequest,
    CreatePredictionRequest,
    CreatePresetRequest,
    CreateSampleRequest,
    CreateScheduleRequest,
    CreateTokenRequest,
    CreateTrainingJobRequest,
    DashboardResponse,
    EditPredictionRequest,
    JobQueueStats,
    LatestAnnotation,
    LatestPrediction,
    LinkLabelStudioRequest,
    LoginRequest,
    LoginResponse,
    MemberResponse,
    MembershipResponse,
    OrgResponse,
    PaginatedResponse,
    RecentJobSummary,
    RegisterRequest,
    RunLogResponse,
    RunResponse,
    ScheduleResponse,
    SampleWithLabels,
    SyncPredictionsResponse,
    TokenCreatedResponse,
    TokenResponse,
    UpdateAnnotationRequest,
    UpdateEmbedConfigRequest,
    UpdateSampleImageResponse,
    UpdateScheduleRequest,
    UserResponse,
    UserWithOrgsResponse,
    WorkPoolStatus,
)
from app.api.deps import get_current_org, get_current_user, require_superadmin
from app.services.scheduler import SchedulerService, get_scheduler_service
from app.container import Container
from app.db.models import OrgMembershipORM, OrganizationORM, PersonalAccessTokenORM, UserORM
from app.db.session import init_db
from app.domain.models import Annotation, Dataset, Organization, PredictionEdit, PredictionResult, Sample, TrainingEvent, TrainingJob, TrainingPreset, User
from app.services.auth import create_access_token, create_personal_access_token, hash_password, verify_password


@asynccontextmanager
async def lifespan(_: FastAPI):
    cfg = container.config()
    if bool(cfg.db.auto_create):
        await init_db(container.db_engine())
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/datasets", response_model=Dataset)
async def create_dataset(
    payload: CreateDatasetRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Dataset:
    dataset = Dataset(name=payload.name, task_spec=payload.task_spec, org_id=org.id)
    dataset = await container.repository().create_dataset(dataset)
    # LS hook: create project if enabled
    cfg = container.config()
    if cfg.label_studio.enabled:
        try:
            from app.services.label_studio import LabelStudioClient as _LSC
            ls_client = container.label_studio_client()
            label_config = _LSC.generate_image_classification_config(
                payload.task_spec.label_space
            )
            project = await ls_client.create_project(payload.name, label_config)
            ls_project_id = str(project.get("id", ""))
            if ls_project_id:
                await container.repository().update_dataset_ls_project_id(
                    dataset.id, ls_project_id
                )
                dataset = dataset.model_copy(update={"ls_project_id": ls_project_id})
        except Exception:
            pass  # LS failure shouldn't break dataset creation
    return dataset


@app.get("/api/v1/datasets", response_model=list[Dataset])
async def list_datasets(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[Dataset]:
    return await container.repository().list_datasets(org_id=org.id)


@app.get("/api/v1/datasets/{dataset_id}", response_model=Dataset)
async def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Dataset:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@app.post("/api/v1/datasets/{dataset_id}/link-ls", response_model=Dataset)
async def link_label_studio(
    dataset_id: str,
    payload: LinkLabelStudioRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Dataset:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await container.repository().update_dataset_ls_project_id(dataset_id, payload.ls_project_id)
    return (await container.repository().get_dataset(dataset_id, org_id=org.id))


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
    sample = Sample(dataset_id=dataset_id, image_uris=payload.image_uris, metadata=payload.metadata)
    sample = await container.repository().create_sample(sample)
    # LS hook: create task if enabled and dataset linked
    cfg = container.config()
    if cfg.label_studio.enabled and dataset.ls_project_id:
        try:
            ls_client = container.label_studio_client()
            image_url = _make_ls_image_url(sample.image_uris[0]) if sample.image_uris else ""
            task = await ls_client.create_task(
                int(dataset.ls_project_id), {"image": image_url}
            )
            ls_task_id = task.get("id")
            if ls_task_id is not None:
                await container.repository().update_sample_ls_task_id(sample.id, int(ls_task_id))
                sample = sample.model_copy(update={"ls_task_id": int(ls_task_id)})
        except Exception:
            pass  # LS failure shouldn't break sample creation
    return sample


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
    ann = Annotation(sample_id=payload.sample_id, label=payload.label, created_by=current_user.id)
    ann = await container.repository().create_annotation(ann)
    # LS hook: sync annotation if enabled and sample linked
    cfg = container.config()
    if cfg.label_studio.enabled and sample.ls_task_id:
        try:
            from app.services.label_studio import platform_annotation_to_ls
            ls_result = platform_annotation_to_ls(payload.label)
            await container.label_studio_client().create_annotation(
                sample.ls_task_id, ls_result
            )
        except Exception:
            pass  # LS failure shouldn't break annotation creation
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

    cfg = container.config()
    if not cfg.label_studio.enabled or not dataset.ls_project_id:
        return {"synced_count": 0, "errors": ["Label Studio not enabled or dataset not linked"]}

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
        if not sample or not sample.ls_task_id:
            continue
        try:
            ls_result = platform_annotation_to_ls(ann.label)
            await ls_client.create_annotation(sample.ls_task_id, ls_result)
            synced_count += 1
        except Exception as e:
            errors.append(f"annotation {ann.id}: {str(e)}")

    return {"synced_count": synced_count, "errors": errors}


@app.post("/api/v1/training-presets", response_model=TrainingPreset)
async def create_preset(
    payload: CreatePresetRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainingPreset:
    preset = TrainingPreset(
        name=payload.name,
        model_spec=payload.model_spec,
        omegaconf_yaml=payload.omegaconf_yaml,
        dataloader_ref=payload.dataloader_ref,
        org_id=org.id,
    )
    return await container.repository().create_preset(preset)


@app.get("/api/v1/training-presets", response_model=list[TrainingPreset])
async def list_presets(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[TrainingPreset]:
    return await container.repository().list_presets(org_id=org.id)


@app.get("/api/v1/training-presets/{preset_id}", response_model=TrainingPreset)
async def get_preset(
    preset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainingPreset:
    preset = await container.repository().get_preset(preset_id, org_id=org.id)
    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset


@app.post("/api/v1/training-jobs", response_model=TrainingJob)
async def create_training_job(
    payload: CreateTrainingJobRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainingJob:
    if await container.repository().get_dataset(payload.dataset_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if await container.repository().get_preset(payload.preset_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="preset not found")
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


@app.post("/api/v1/predictions", response_model=PredictionResult)
async def create_prediction(
    payload: CreatePredictionRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PredictionResult:
    if await container.repository().get_sample(payload.sample_id) is None:
        raise HTTPException(status_code=404, detail="sample not found")
    pred = PredictionResult(
        sample_id=payload.sample_id,
        predicted_label=payload.predicted_label,
        score=payload.score,
        model_artifact_id=payload.model_artifact_id,
    )
    return await container.repository().create_prediction(pred)


@app.get("/api/v1/predictions", response_model=list[PredictionResult])
async def list_predictions(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[PredictionResult]:
    return await container.repository().list_predictions()


@app.patch("/api/v1/predictions/{prediction_id}", response_model=PredictionEdit)
async def edit_prediction(
    prediction_id: str,
    payload: EditPredictionRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PredictionEdit:
    if await container.repository().get_prediction(prediction_id) is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    edit = PredictionEdit(result_id=prediction_id, corrected_label=payload.corrected_label, edited_by=current_user.id)
    return await container.repository().create_prediction_edit(edit)


@app.post("/api/v1/datasets/{dataset_id}/sync-predictions-to-ls", response_model=SyncPredictionsResponse)
async def sync_predictions_to_ls(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SyncPredictionsResponse:
    dataset = await container.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    cfg = container.config()
    if not cfg.label_studio.enabled or not dataset.ls_project_id:
        return SyncPredictionsResponse(
            synced_count=0, skipped_count=0,
            errors=["Label Studio not enabled or dataset not linked"]
        )

    # Get predictions for this dataset's samples
    predictions = await container.repository().list_predictions_for_dataset(dataset_id)
    if not predictions:
        return SyncPredictionsResponse(synced_count=0, skipped_count=0, errors=[])

    # Get sample map for ls_task_id lookup
    samples, _ = await container.repository().list_samples(dataset_id, limit=100_000)
    sample_map = {s.id: s for s in samples}

    from app.services.label_studio import platform_prediction_to_ls

    ls_predictions = []
    skipped = 0
    for pred in predictions:
        sample = sample_map.get(pred.sample_id)
        if not sample or not sample.ls_task_id:
            skipped += 1
            continue
        ls_pred = platform_prediction_to_ls(
            predicted_label=pred.predicted_label,
            score=pred.score,
            task_id=sample.ls_task_id,
            model_version=pred.model_artifact_id,
        )
        ls_predictions.append(ls_pred)

    synced = 0
    errors = []
    ls_client = container.label_studio_client()

    # Batch import (100 at a time)
    batch_size = 100
    for i in range(0, len(ls_predictions), batch_size):
        batch = ls_predictions[i:i + batch_size]
        try:
            await ls_client.import_predictions(int(dataset.ls_project_id), batch)
            synced += len(batch)
        except Exception as e:
            errors.append(f"batch {i // batch_size}: {str(e)}")

    return SyncPredictionsResponse(synced_count=synced, skipped_count=skipped, errors=errors)


_logger = logging.getLogger(__name__)


async def _build_export_data(dataset_id: str):
    """Return (dataset, samples, annotations) — sourcing from LS when appropriate.

    If Label Studio is enabled and the dataset has an ``ls_project_id``, tasks
    and annotations are fetched from LS and converted to the platform format.
    On any LS failure the function falls back to the local repository data and
    logs a warning.
    """
    from app.services.label_studio import ls_annotation_to_platform

    repo = container.repository()
    dataset = await repo.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")

    cfg = container.config()
    ls_enabled = bool(getattr(cfg, "label_studio", None) and cfg.label_studio.enabled)

    if ls_enabled and dataset.ls_project_id:
        try:
            ls_client = container.label_studio_client()
            ls_tasks = await ls_client.export_project(int(dataset.ls_project_id))

            # Build a lookup: ls_task_id → platform Sample
            all_samples, _ = await repo.list_samples(dataset_id, limit=100_000)
            task_id_to_sample: dict[int, Sample] = {
                s.ls_task_id: s for s in all_samples if s.ls_task_id is not None
            }

            samples_out: list[Sample] = []
            annotations_out: list[Annotation] = []

            for ls_task in ls_tasks:
                task_id = ls_task.get("id")
                platform_sample = task_id_to_sample.get(task_id) if task_id is not None else None

                if platform_sample is None:
                    # LS task has no matching platform sample — skip
                    continue

                samples_out.append(platform_sample)

                for ls_ann in ls_task.get("annotations", []):
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

            # Include any platform samples that have no LS task (no duplicates)
            ls_task_ids_seen = {s.ls_task_id for s in samples_out}
            for s in all_samples:
                if s.ls_task_id not in ls_task_ids_seen or s.ls_task_id is None:
                    if s not in samples_out:
                        samples_out.append(s)

            return dataset, samples_out, annotations_out

        except Exception as exc:
            _logger.warning(
                "LS export failed for dataset %s project %s — falling back to local data: %s",
                dataset_id,
                dataset.ls_project_id,
                exc,
            )

    # Default: use local repository data
    samples, _ = await repo.list_samples(dataset_id, limit=100_000)
    anns = await repo.list_annotations_for_dataset(dataset_id)
    return dataset, samples, anns


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

    # Count total samples
    samples, total = await container.repository().list_samples(dataset_id, limit=100_000)

    # Determine which samples need embedding via direct check
    # (efficient: avoid loading full ORM objects where possible)
    to_embed: list[str] = []
    for s in samples:
        feature = await container.repository().get_sample_feature(s.id)
        if feature is None or feature.embed_model != embed_model or force:
            to_embed.append(s.id)

    async def _background_embed() -> None:
        storage = container.artifact_storage()
        embedding_svc = container.embedding_service()
        repo = container.repository()
        for sid in to_embed:
            sample = await repo.get_sample(sid)
            if sample is None or not sample.image_uris:
                continue
            uri = sample.image_uris[0]
            try:
                if uri.startswith("data:"):
                    _, encoded = uri.split(",", 1)
                    image_bytes = base64.b64decode(encoded)
                else:
                    image_bytes = await storage.get_bytes(uri)
                embedding = await embedding_svc.embed_image(image_bytes, model_name=embed_model)
                await repo.upsert_sample_feature(sid, embedding, embed_model)
            except Exception:
                pass  # Don't let one failure stop the batch

    asyncio.create_task(_background_embed())

    return {"status": "processing", "total_samples": total, "to_embed": len(to_embed)}


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
        "uniqueness": fs.uniqueness_scores(sample_ids),
        "representativeness": fs.representativeness_scores(sample_ids),
    }


@app.get("/api/v1/datasets/{dataset_id}/hints/uncovered")
async def uncovered_hints(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    if await container.repository().get_dataset(dataset_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return container.feature_ops().uncovered_cluster_hints(dataset_id)


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
        ls_enabled = bool(getattr(cfg, "label_studio", None) and cfg.label_studio.enabled)
        ls_url = str(cfg.label_studio.url).rstrip("/") if ls_enabled else ""
        if not (ls_enabled and ls_url and uri.startswith(ls_url)):
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

    return DashboardResponse(
        work_pool=work_pool,
        job_queue=stats,
        recent_jobs=recent,
        prefect_connected=prefect_connected,
    )


# ---------------------------------------------------------------------------
# Schedule endpoints (Prefect-backed)
# ---------------------------------------------------------------------------


def _deployment_to_schedule(raw: dict) -> ScheduleResponse:
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
        prefect_deployment_id=raw.get("id", ""),
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
    raws = await svc.list_schedules()
    return [_deployment_to_schedule(r) for r in raws]


@app.get("/api/v1/schedules/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    svc: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleResponse:
    raw = await svc.get_schedule(schedule_id)
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
