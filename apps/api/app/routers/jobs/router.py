from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.deps import get_current_org, get_current_user, require_superadmin
from app.api.schemas import (
    CancelJobResponse,
    CreateReviewActionRequest,
    CreateTrainingJobRequest,
    ExportFormatResponse,
    MarkLeftResponse,
    ModelUploadTemplateResponse,
    PaginatedResponse,
    PredictionCollectionRequest,
    PredictionCollectionResponse,
    PredictionEventResponse,
    PredictionJobResponse,
    PredictionResultResponse,
    PredictSingleRequest,
    ReviewActionResponse,
    RunPredictionRequest,
    SaveReviewAnnotationsRequest,
    SaveReviewAnnotationsResponse,
    SetPublicRequest,
    SetPublicResponse,
    SyncPredictionCollectionRequest,
    SyncPredictionCollectionResponse,
    AnnotationVersionResponse,
    VersionExportPersistResponse,
    VersionExportRequest,
    UploadTemplateProfileResponse,
)
from app.domain.models import Organization, TrainingEvent, TrainingJob, User
from app.routers._common import get_container
from app.services.compatibility import (
    validate_dataset_preset_training,
    UPLOAD_TEMPLATE_DEFINITIONS,
)
from app.services.dataset_capability_guard import assert_not_sparse

router = APIRouter(prefix="/api/v1", tags=["jobs"])
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Training Presets
# ---------------------------------------------------------------------------


@router.get("/training-presets")
async def list_presets(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[dict]:
    c = get_container()
    registry = c.preset_registry()
    return [registry.preset_to_api_dict(p) for p in registry.list_presets()]


@router.get("/training-presets/{preset_id}")
async def get_preset(
    preset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    c = get_container()
    registry = c.preset_registry()
    spec = registry.get_preset(preset_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return registry.preset_to_api_dict(spec)


# ---------------------------------------------------------------------------
# Training Jobs
# ---------------------------------------------------------------------------


@router.post("/training-jobs", response_model=TrainingJob)
async def create_training_job(
    payload: CreateTrainingJobRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainingJob:
    c = get_container()
    dataset = await c.repository().get_dataset(payload.dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    assert_not_sparse(dataset)
    registry = c.preset_registry()
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
    job = TrainingJob(
        dataset_id=payload.dataset_id,
        preset_id=payload.preset_id,
        created_by=current_user.id,
        org_id=org.id,
    )
    try:
        return await c.orchestrator().start_job(job)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to start training job: {exc}"
        )


@router.get("/training-jobs", response_model=list[TrainingJob])
async def list_jobs(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[TrainingJob]:
    c = get_container()
    return await c.repository().list_jobs(org_id=org.id)


@router.get("/training-jobs/{job_id}", response_model=TrainingJob)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TrainingJob:
    c = get_container()
    job = await c.repository().get_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/training-jobs/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CancelJobResponse:
    c = get_container()
    try:
        ok = await c.orchestrator().cancel_job(job_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to cancel job: {exc}")
    return CancelJobResponse(cancelled=ok)


@router.get("/training-jobs/{job_id}/events")
async def get_job_events(
    job_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    import asyncio

    from fastapi.responses import StreamingResponse

    c = get_container()
    if await c.repository().get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_stream():
        idx = 0
        while True:
            if await request.is_disconnected():
                break
            events = await c.repository().list_events(job_id)
            while idx < len(events):
                line = f"data: {json.dumps(events[idx].model_dump(mode='json'))}\n\n"
                yield line
                idx += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get(
    "/training-jobs/{job_id}/events/history",
    response_model=PaginatedResponse[TrainingEvent],
)
async def get_job_events_history(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PaginatedResponse[TrainingEvent]:
    c = get_container()
    if await c.repository().get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    items, total = await c.repository().list_events_paginated(
        job_id, offset=offset, limit=limit
    )
    return PaginatedResponse(items=items, total=total)


@router.post("/training-jobs/{job_id}/mark-left", response_model=MarkLeftResponse)
async def mark_user_left(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> MarkLeftResponse:
    c = get_container()
    if await c.repository().get_job(job_id, org_id=org.id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    return MarkLeftResponse(marked=await c.repository().mark_user_left(job_id))


@router.patch("/training-jobs/{job_id}/public", response_model=SetPublicResponse)
async def set_job_public(
    job_id: str,
    payload: SetPublicRequest,
    current_user: User = Depends(get_current_user),
) -> SetPublicResponse:
    c = get_container()
    await require_superadmin(current_user=current_user)
    ok = await c.repository().set_job_public(job_id, payload.is_public)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return SetPublicResponse(ok=True)


# ---------------------------------------------------------------------------
# Prediction helpers
# ---------------------------------------------------------------------------


def _prediction_result_to_response(result) -> PredictionResultResponse:
    return PredictionResultResponse(
        id=result.id,
        sample_id=result.sample_id,
        predicted_label=result.predicted_label,
        confidence=result.confidence,
        model_id=result.model_id,
        target=result.target,
        model_version=result.model_version,
        job_id=result.job_id,
        created_at=result.created_at,
        error=result.error,
    )


def _prediction_collection_to_response(
    collection, prediction_ids: list[str]
) -> PredictionCollectionResponse:
    return PredictionCollectionResponse(
        id=collection.id,
        name=collection.name,
        dataset_id=collection.dataset_id,
        model_id=collection.model_id,
        model_version=collection.model_version,
        target=collection.target,
        source_job_id=collection.source_job_id,
        sync_tag=collection.sync_tag,
        created_by=collection.created_by,
        created_at=collection.created_at,
        prediction_ids=prediction_ids,
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


# ---------------------------------------------------------------------------
# Prediction endpoints
# ---------------------------------------------------------------------------


@router.post("/predictions/run", response_model=PredictionJobResponse, status_code=202)
async def run_predictions(
    payload: RunPredictionRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PredictionJobResponse:
    c = get_container()
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
        if str(c.config().app.env) == "test":
            from app.domain.models import PredictionEvent
            from app.domain.types import JobStatus

            result = await c.prediction_service().run_prediction(
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
            persisted = await c.repository().create_prediction_job(job, org_id=org.id)
            await c.repository().add_prediction_event(
                PredictionEvent(
                    job_id=persisted.id,
                    message="prediction completed in test mode",
                    payload={"summary": persisted.summary},
                )
            )
            return _prediction_job_to_response(persisted)
        try:
            started = await c.prediction_orchestrator().start_job(job)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Failed to start prediction job: {exc}"
            )
        return _prediction_job_to_response(started)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/prediction-jobs", response_model=list[PredictionJobResponse])
async def list_prediction_jobs(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[PredictionJobResponse]:
    c = get_container()
    jobs = await c.repository().list_prediction_jobs(org_id=org.id)
    return [_prediction_job_to_response(job) for job in jobs]


@router.get("/prediction-jobs/{job_id}", response_model=PredictionJobResponse)
async def get_prediction_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PredictionJobResponse:
    c = get_container()
    job = await c.repository().get_prediction_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Prediction job not found")
    return _prediction_job_to_response(job)


@router.get(
    "/prediction-jobs/{job_id}/predictions",
    response_model=list[PredictionResultResponse],
)
async def list_prediction_job_predictions(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[PredictionResultResponse]:
    c = get_container()
    job = await c.repository().get_prediction_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Prediction job not found")
    predictions = await c.prediction_service().list_predictions_for_job(
        job_id, org_id=org.id
    )
    return [_prediction_result_to_response(item) for item in predictions]


@router.get(
    "/prediction-jobs/{job_id}/events",
    response_model=list[PredictionEventResponse],
)
async def list_prediction_job_events(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[PredictionEventResponse]:
    c = get_container()
    job = await c.repository().get_prediction_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Prediction job not found")
    events = await c.repository().list_prediction_events(job_id)
    return [
        PredictionEventResponse(
            job_id=e.job_id,
            ts=e.ts,
            level=e.level,
            message=e.message,
            payload=e.payload,
        )
        for e in events
    ]


@router.post("/prediction-jobs/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_prediction_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CancelJobResponse:
    c = get_container()
    cancelled = await c.prediction_orchestrator().cancel_job(job_id, org_id=org.id)
    if not cancelled:
        raise HTTPException(
            status_code=404, detail="Prediction job not found or not cancellable"
        )
    return CancelJobResponse(cancelled=True)


@router.post("/predictions/single", response_model=PredictionResultResponse)
async def predict_single(
    payload: PredictSingleRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PredictionResultResponse:
    c = get_container()
    try:
        result = await c.prediction_service().predict_single(
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


@router.get(
    "/samples/{sample_id}/predictions",
    response_model=list[PredictionResultResponse],
)
async def list_sample_predictions(
    sample_id: str,
    model_version: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[PredictionResultResponse]:
    c = get_container()
    try:
        predictions = await c.prediction_service().list_predictions_for_sample(
            sample_id=sample_id,
            org_id=org.id,
            model_version=model_version,
        )
        return [_prediction_result_to_response(item) for item in predictions]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Prediction Collections
# ---------------------------------------------------------------------------


@router.post(
    "/prediction-collections",
    response_model=PredictionCollectionResponse,
    status_code=201,
)
async def create_prediction_collection(
    payload: PredictionCollectionRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PredictionCollectionResponse:
    c = get_container()
    try:
        collection = await c.prediction_service().create_prediction_collection(
            dataset_id=payload.dataset_id,
            model_id=payload.model_id,
            org_id=org.id,
            created_by=current_user.id,
            prediction_ids=payload.prediction_ids,
            name=payload.name,
            model_version=payload.model_version,
            target=payload.target,
            source_job_id=payload.source_job_id,
        )
        return _prediction_collection_to_response(collection, payload.prediction_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/prediction-collections", response_model=list[PredictionCollectionResponse]
)
async def list_prediction_collections(
    dataset_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[PredictionCollectionResponse]:
    c = get_container()
    collections = await c.prediction_service().list_prediction_collections(
        dataset_id, org_id=org.id
    )
    responses: list[PredictionCollectionResponse] = []
    for collection in collections:
        predictions = await c.repository().list_prediction_collection_predictions(
            collection.id, org.id
        )
        responses.append(
            _prediction_collection_to_response(
                collection, [item.id for item in predictions]
            )
        )
    return responses


@router.post(
    "/prediction-collections/{collection_id}/sync-label-studio",
    response_model=SyncPredictionCollectionResponse,
)
async def sync_prediction_collection_to_label_studio(
    collection_id: str,
    payload: SyncPredictionCollectionRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SyncPredictionCollectionResponse:
    c = get_container()
    try:
        (
            collection,
            synced_count,
            failed_count,
            errors,
        ) = await c.prediction_service().sync_prediction_collection_to_label_studio(
            collection_id=collection_id,
            org_id=org.id,
            sync_tag=payload.sync_tag,
        )
        return SyncPredictionCollectionResponse(
            collection_id=collection.id,
            sync_tag=collection.sync_tag or payload.sync_tag or "",
            synced_count=synced_count,
            failed_count=failed_count,
            errors=errors,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Prediction Reviews
# ---------------------------------------------------------------------------


@router.post(
    "/prediction-reviews", response_model=ReviewActionResponse, status_code=201
)
async def create_review_action(
    payload: CreateReviewActionRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ReviewActionResponse:
    c = get_container()
    try:
        action = await c.prediction_service().create_review_action(
            dataset_id=payload.dataset_id,
            model_id=payload.model_id,
            org_id=org.id,
            created_by=current_user.id,
            model_version=payload.model_version,
            collection_id=payload.collection_id,
            sync_tag=payload.sync_tag,
        )
        return ReviewActionResponse(
            id=action.id,
            dataset_id=action.dataset_id,
            model_id=action.model_id,
            model_version=action.model_version,
            collection_id=action.collection_id,
            sync_tag=action.sync_tag,
            created_by=action.created_by,
            created_at=action.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/prediction-reviews", response_model=list[ReviewActionResponse])
async def list_review_actions(
    dataset_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[ReviewActionResponse]:
    c = get_container()
    actions = await c.repository().list_review_actions(dataset_id)
    return [
        ReviewActionResponse(
            id=a.id,
            dataset_id=a.dataset_id,
            model_id=a.model_id,
            model_version=a.model_version,
            collection_id=a.collection_id,
            sync_tag=a.sync_tag,
            created_by=a.created_by,
            created_at=a.created_at,
        )
        for a in actions
    ]


@router.get("/prediction-reviews/{action_id}", response_model=ReviewActionResponse)
async def get_review_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ReviewActionResponse:
    c = get_container()
    action = await c.repository().get_review_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")
    return ReviewActionResponse(
        id=action.id,
        dataset_id=action.dataset_id,
        model_id=action.model_id,
        model_version=action.model_version,
        collection_id=action.collection_id,
        sync_tag=action.sync_tag,
        created_by=action.created_by,
        created_at=action.created_at,
    )


@router.delete("/prediction-reviews/{action_id}", status_code=204)
async def delete_review_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    c = get_container()
    deleted = await c.repository().delete_review_action(action_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Review action not found")
    return Response(status_code=204)


@router.post(
    "/prediction-reviews/{action_id}/annotations",
    response_model=SaveReviewAnnotationsResponse,
)
async def save_review_annotations(
    action_id: str,
    payload: SaveReviewAnnotationsRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SaveReviewAnnotationsResponse:
    c = get_container()
    action = await c.repository().get_review_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")
    dataset = await c.repository().get_dataset(action.dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    assert_not_sparse(dataset)
    try:
        items = [item.model_dump() for item in payload.items]
        (
            _annotations,
            versions,
        ) = await c.prediction_service().save_review_annotations(
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
                    prediction_id=v.prediction_id,
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


@router.get(
    "/prediction-reviews/{action_id}/annotation-versions",
    response_model=list[AnnotationVersionResponse],
)
async def list_annotation_versions(
    action_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[AnnotationVersionResponse]:
    c = get_container()
    action = await c.repository().get_review_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")
    versions = await c.repository().list_annotation_versions(action_id)
    return [
        AnnotationVersionResponse(
            id=v.id,
            review_action_id=v.review_action_id,
            annotation_id=v.annotation_id,
            prediction_id=v.prediction_id,
            predicted_label=v.predicted_label,
            final_label=v.final_label,
            confidence=v.confidence,
            created_at=v.created_at,
        )
        for v in versions
    ]


# ---------------------------------------------------------------------------
# Export formats & version export
# ---------------------------------------------------------------------------


@router.get("/export-formats", response_model=list[ExportFormatResponse])
async def list_export_formats(
    current_user: User = Depends(get_current_user),
) -> list[ExportFormatResponse]:
    from app.services.artifacts import list_export_formats as _list_fmts

    return [ExportFormatResponse(format_id=f["format_id"]) for f in _list_fmts()]


@router.get("/prediction-reviews/{action_id}/export")
async def export_review_version(
    action_id: str,
    format_id: str = Query(default="annotation-version-full-context-v1"),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    from app.services.artifacts import get_export_builder

    c = get_container()
    action = await c.repository().get_review_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")

    try:
        builder = get_export_builder(format_id)
    except KeyError:
        raise HTTPException(
            status_code=400, detail=f"Unknown export format: {format_id}"
        )

    repo = c.repository()
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

    return builder(
        review_action=action,
        dataset=dataset,
        samples=samples,
        annotations=annotations,
        versions=versions,
    )


@router.post(
    "/prediction-reviews/{action_id}/export/persist",
    response_model=VersionExportPersistResponse,
)
async def persist_review_export(
    action_id: str,
    payload: VersionExportRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> VersionExportPersistResponse:
    c = get_container()
    action = await c.repository().get_review_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")

    repo = c.repository()
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
        uri = await c.artifacts().persist_version_export(
            review_action=action,
            dataset=dataset,
            samples=samples,
            annotations=annotations,
            versions=versions,
            format_id=payload.format_id,
        )
    except KeyError:
        raise HTTPException(
            status_code=400, detail=f"Unknown export format: {payload.format_id}"
        )

    return VersionExportPersistResponse(uri=uri, format_id=payload.format_id)


# ---------------------------------------------------------------------------
# Feature extraction (dataset-level)
# ---------------------------------------------------------------------------


@router.post(
    "/datasets/{dataset_id}/features/extract",
    response_model=PredictionJobResponse,
)
async def extract_features(
    dataset_id: str,
    force: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    c = get_container()
    dataset = await c.repository().get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    assert_not_sparse(dataset)

    embed_model: str = (dataset.embed_config or {}).get(
        "model", "openai/clip-vit-base-patch32"
    )
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
    if str(c.config().app.env) == "test":
        from app.domain.types import JobStatus

        samples, total = await c.repository().list_samples(dataset_id, limit=100_000)
        result = await c.feature_ops().extract_features(
            samples=samples,
            embed_model=embed_model,
            force=force,
            storage=c.artifact_storage(),
        )
        job.status = JobStatus.COMPLETED
        job.summary = {
            "status": result.get("status", "completed"),
            "total_samples": total,
            "processed": result.get("computed", 0),
            "skipped": result.get("skipped", 0),
            "embedding_model": result.get("embedding_model", embed_model),
        }
        persisted = await c.repository().create_prediction_job(job, org_id=org.id)
        return _prediction_job_to_response(persisted).model_dump()
    try:
        started = await c.prediction_orchestrator().start_job(job)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to start feature extraction: {exc}"
        )
    return _prediction_job_to_response(started).model_dump()


# ---------------------------------------------------------------------------
# Model upload templates
# ---------------------------------------------------------------------------


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
