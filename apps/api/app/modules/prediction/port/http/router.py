from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.datasets.port.http.deps import get_dataset_storage_factory
from app.modules.datasets.port.local import DatasetCompatibilityError
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.prediction.port.http.deps import (
    ArtifactServiceDep,
    DatasetReaderDep,
    DatasetServiceDep,
    PredictionCollectionDep,
    PredictionSubmissionDep,
    PredictionQueryDep,
    PredictionRepositoryDep,
    PredictionReviewDep,
    PredictionRuntimeDep,
    RedisEventPublisherDep,
)
from app.modules.prediction.domain.submission import (
    PredictionResourceNotFoundError,
    PredictionRuntimeUnavailableError,
    PredictionSubmissionError,
    PredictionSubmissionRejectedError,
)
from app.modules.prediction.port.http.schemas import (
    CreateReviewActionRequest,
    ExportFormatResponse,
    AnnotationVersionResponse,
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
    SyncPredictionCollectionRequest,
    SyncPredictionCollectionResponse,
    VersionExportPersistResponse,
    VersionExportRequest,
)
from app.shared.api.schemas import Organization, User
from app.shared.api.schemas import CancelJobResponse, PaginatedResponse

router = APIRouter(prefix="/api/v1", tags=["prediction"])
CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentOrgDep = Annotated[Organization, Depends(get_current_org)]
DatasetStorageFactoryDep = Annotated[
    DatasetStorageFactoryPort, Depends(get_dataset_storage_factory)
]


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
        dataset_revision_id=job.dataset_revision_id,
        collection_id=job.collection_id,
        collection_revision_id=job.collection_revision_id,
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
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    prediction_submission: PredictionSubmissionDep,
) -> PredictionJobResponse:
    try:
        started = await prediction_submission.submit_job(
            payload.to_command(org_id=org.id, created_by=current_user.id)
        )
    except PredictionResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PredictionSubmissionRejectedError, DatasetCompatibilityError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PredictionRuntimeUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PredictionSubmissionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _prediction_job_to_response(started)


@router.get(
    "/prediction-jobs",
    response_model=PaginatedResponse[PredictionJobResponse],
)
async def list_prediction_jobs(
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
    dataset_id: str | None = Query(
        default=None,
        description="Filter prediction jobs to one dataset.",
    ),
    collection_id: str | None = Query(
        default=None,
        description="Filter prediction jobs to one dataset collection.",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PaginatedResponse[PredictionJobResponse]:
    jobs, total = await repo.list_prediction_jobs_paginated(
        org_id=org.id,
        dataset_id=dataset_id,
        collection_id=collection_id,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse(
        items=[_prediction_job_to_response(job) for job in jobs],
        total=total,
    )


@router.get("/prediction-jobs/{job_id}", response_model=PredictionJobResponse)
async def get_prediction_job(
    job_id: str,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
) -> PredictionJobResponse:
    job = await repo.get_prediction_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Prediction job not found")
    return _prediction_job_to_response(job)


@router.get(
    "/prediction-jobs/{job_id}/predictions",
    response_model=list[PredictionResultResponse],
)
async def list_prediction_job_predictions(
    job_id: str,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
    prediction_query: PredictionQueryDep,
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    limit: int = Query(1000, ge=1, le=10000, description="Max results to return"),
) -> list[PredictionResultResponse]:
    job = await repo.get_prediction_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Prediction job not found")
    predictions = await prediction_query.list_predictions_for_job(
        job_id, org_id=org.id, offset=offset, limit=limit
    )
    return [_prediction_result_to_response(item) for item in predictions]


@router.get(
    "/prediction-jobs/{job_id}/events",
    response_model=PaginatedResponse[PredictionEventResponse],
)
async def list_prediction_job_events(
    job_id: str,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PaginatedResponse[PredictionEventResponse]:
    job = await repo.get_prediction_job(job_id, org_id=org.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Prediction job not found")
    events, total = await repo.list_prediction_events_paginated(
        job_id,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse(
        items=[
            PredictionEventResponse(
                job_id=event.job_id,
                ts=event.ts,
                level=event.level,
                message=event.message,
                payload=event.payload,
            )
            for event in events
        ],
        total=total,
    )


@router.post("/prediction-jobs/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_prediction_job(
    job_id: str,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    prediction_submission: PredictionSubmissionDep,
) -> CancelJobResponse:
    cancelled = await prediction_submission.cancel_job(job_id, org_id=org.id)
    if not cancelled:
        raise HTTPException(
            status_code=404, detail="Prediction job not found or not cancellable"
        )
    return CancelJobResponse(cancelled=True)


@router.post("/predictions/single", response_model=PredictionResultResponse)
async def predict_single(
    payload: PredictSingleRequest,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    prediction_runtime: PredictionRuntimeDep,
) -> PredictionResultResponse:
    try:
        result = await prediction_runtime.predict_single(
            model_id=payload.model_id,
            dataset_id=payload.dataset_id,
            sample_id=payload.sample_id,
            org_id=org.id,
            model_version=payload.model_version,
            target=payload.target,
            prompt=payload.prompt,
            predictor_id=payload.predictor_id,
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
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    prediction_query: PredictionQueryDep,
    dataset_id: str | None = Query(
        default=None, description="Dataset ID (required for sparse datasets)"
    ),
    model_version: str | None = Query(default=None),
) -> list[PredictionResultResponse]:
    try:
        predictions = await prediction_query.list_predictions_for_sample(
            sample_id=sample_id,
            org_id=org.id,
            dataset_id=dataset_id,
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
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    prediction_collection: PredictionCollectionDep,
) -> PredictionCollectionResponse:
    try:
        collection = await prediction_collection.create_prediction_collection(
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
    "/prediction-collections",
    response_model=PaginatedResponse[PredictionCollectionResponse],
)
async def list_prediction_collections(
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
    dataset_id: str = Query(...),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PaginatedResponse[PredictionCollectionResponse]:
    collections, total = await repo.list_prediction_collections_paginated(
        dataset_id,
        org.id,
        offset=offset,
        limit=limit,
    )
    prediction_ids_by_collection = await repo.list_prediction_ids_by_collection(
        [collection.id for collection in collections],
        org.id,
    )
    return PaginatedResponse(
        items=[
            _prediction_collection_to_response(
                collection,
                prediction_ids_by_collection[collection.id],
            )
            for collection in collections
        ],
        total=total,
    )


@router.post(
    "/prediction-collections/{collection_id}/sync-label-studio",
    response_model=SyncPredictionCollectionResponse,
)
async def sync_prediction_collection_to_label_studio(
    collection_id: str,
    payload: SyncPredictionCollectionRequest,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    prediction_collection: PredictionCollectionDep,
) -> SyncPredictionCollectionResponse:
    try:
        (
            collection,
            synced_count,
            failed_count,
            errors,
        ) = await prediction_collection.sync_prediction_collection_to_label_studio(
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
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    prediction_review: PredictionReviewDep,
) -> ReviewActionResponse:
    try:
        action = await prediction_review.create_review_action(
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


@router.get(
    "/prediction-reviews",
    response_model=PaginatedResponse[ReviewActionResponse],
)
async def list_review_actions(
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
    dataset_id: str = Query(...),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PaginatedResponse[ReviewActionResponse]:
    actions, total = await repo.list_review_actions_paginated(
        dataset_id,
        org.id,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse(
        items=[
            ReviewActionResponse(
                id=action.id,
                dataset_id=action.dataset_id,
                model_id=action.model_id,
                model_version=action.model_version,
                collection_id=action.collection_id,
                sync_tag=action.sync_tag,
                created_by=action.created_by,
                created_at=action.created_at,
            )
            for action in actions
        ],
        total=total,
    )


@router.get("/prediction-reviews/{action_id}", response_model=ReviewActionResponse)
async def get_review_action(
    action_id: str,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
) -> ReviewActionResponse:
    action = await repo.get_review_action(action_id, org.id)
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
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
) -> Response:
    deleted = await repo.delete_review_action(action_id, org.id)
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
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
    dataset_reader: DatasetReaderDep,
    prediction_review: PredictionReviewDep,
    dataset_service: DatasetServiceDep,
    event_publisher: RedisEventPublisherDep,
) -> SaveReviewAnnotationsResponse:
    action = await repo.get_review_action(action_id, org.id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")
    dataset = await dataset_reader.get_dataset(action.dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        items = [item.to_command() for item in payload.items]
        (
            annotations,
            versions,
        ) = await prediction_review.save_review_annotations(
            review_action_id=action_id,
            items=items,
            created_by=current_user.id,
            org_id=org.id,
        )
        # Auto-expand label_space with final_labels from annotations
        incoming_labels = {
            item.final_label for item in payload.items if item.final_label
        }
        if incoming_labels:
            await dataset_service.merge_label_space(
                dataset.id,
                org.id,
                incoming_labels,
            )

        if annotations or versions:
            await event_publisher.publish_prediction_refresh(
                dataset_id=dataset.id,
                job_id="",
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
    response_model=PaginatedResponse[AnnotationVersionResponse],
)
async def list_annotation_versions(
    action_id: str,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PaginatedResponse[AnnotationVersionResponse]:
    action = await repo.get_review_action(action_id, org.id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")
    versions, total = await repo.list_annotation_versions_paginated(
        action_id,
        offset=offset,
        limit=limit,
    )
    return PaginatedResponse(
        items=[
            AnnotationVersionResponse(
                id=version.id,
                review_action_id=version.review_action_id,
                annotation_id=version.annotation_id,
                prediction_id=version.prediction_id,
                predicted_label=version.predicted_label,
                final_label=version.final_label,
                confidence=version.confidence,
                created_at=version.created_at,
            )
            for version in versions
        ],
        total=total,
    )


# ---------------------------------------------------------------------------
# Export formats & version export
# ---------------------------------------------------------------------------


@router.get("/export-formats", response_model=list[ExportFormatResponse])
async def list_export_formats(
    current_user: CurrentUserDep,
) -> list[ExportFormatResponse]:
    from app.shared.application.artifacts import list_export_formats as _list_fmts

    return [ExportFormatResponse(format_id=f["format_id"]) for f in _list_fmts()]


@router.get("/prediction-reviews/{action_id}/export")
async def export_review_version(
    action_id: str,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
    dataset_reader: DatasetReaderDep,
    factory: DatasetStorageFactoryDep,
    format_id: str = Query(default="annotation-version-full-context-v1"),
) -> dict:
    from app.shared.application.artifacts import get_export_builder

    action = await repo.get_review_action(action_id, org.id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")

    try:
        builder = get_export_builder(format_id)
    except KeyError:
        raise HTTPException(
            status_code=400, detail=f"Unknown export format: {format_id}"
        )

    dataset = await dataset_reader.get_dataset(action.dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    storage = await factory.open(action.dataset_id, org_id=org.id)
    versions = await repo.list_annotation_versions(action_id)
    ann_ids = list(dict.fromkeys(v.annotation_id for v in versions))
    annotations = await storage.get_annotations_batch(ann_ids)
    sample_ids_set = {annotation.sample_id for annotation in annotations}

    from app.shared.api.schemas import Sample as SampleSchema

    sample_id_list = list(sample_ids_set)
    rows_by_id = await storage.get_samples_by_id(sample_id_list)
    samples: list = []
    for sid in sample_id_list:
        row = rows_by_id.get(sid)
        if row is not None:
            samples.append(
                SampleSchema(
                    id=row.sample_id,
                    dataset_id=row.dataset_id,
                    image_uris=row.image_uris,
                    metadata=row.metadata,
                )
            )

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
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: PredictionRepositoryDep,
    dataset_reader: DatasetReaderDep,
    factory: DatasetStorageFactoryDep,
    artifacts: ArtifactServiceDep,
) -> VersionExportPersistResponse:
    action = await repo.get_review_action(action_id, org.id)
    if action is None:
        raise HTTPException(status_code=404, detail="Review action not found")

    dataset = await dataset_reader.get_dataset(action.dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    storage = await factory.open(action.dataset_id, org_id=org.id)
    versions = await repo.list_annotation_versions(action_id)
    ann_ids = list(dict.fromkeys(v.annotation_id for v in versions))
    annotations = await storage.get_annotations_batch(ann_ids)
    sample_ids_set = {annotation.sample_id for annotation in annotations}

    from app.shared.api.schemas import Sample as SampleSchema

    sample_id_list = list(sample_ids_set)
    rows_by_id = await storage.get_samples_by_id(sample_id_list)
    samples: list = []
    for sid in sample_id_list:
        row = rows_by_id.get(sid)
        if row is not None:
            samples.append(
                SampleSchema(
                    id=row.sample_id,
                    dataset_id=row.dataset_id,
                    image_uris=row.image_uris,
                    metadata=row.metadata,
                )
            )

    try:
        uri = await artifacts.persist_version_export(
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
