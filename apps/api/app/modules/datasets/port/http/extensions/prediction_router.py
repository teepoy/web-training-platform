from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.prediction.port.http.deps import (
    ArtifactStorageDep,
    BatchPredictionServiceDep,
    ConfigDep,
    FeatureOpsServiceDep,
    PredictionOrchestratorDep,
    PredictionRepositoryDep,
    SqlRepositoryDep,
)
from app.modules.prediction.port.http.schemas import (
    PredictionJobResponse,
    PredictionResultResponse,
)
from app.shared.api.schemas import Organization, User
from app.modules.datasets.port.http.deps import (
    get_dataset_storage_factory,
)
from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory


router = APIRouter(prefix="/api/v1", tags=["datasets"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentOrgDep = Annotated[Organization, Depends(get_current_org)]


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


@router.post(
    "/datasets/{dataset_id}/features/extract",
    response_model=PredictionJobResponse,
)
async def extract_features(
    dataset_id: str,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    cfg: ConfigDep,
    repo: PredictionRepositoryDep,
    storage: ArtifactStorageDep,
    feature_ops: FeatureOpsServiceDep,
    prediction_orchestrator: PredictionOrchestratorDep,
    factory: DatasetStorageFactory = Depends(get_dataset_storage_factory),
    force: bool = Query(default=False),
) -> dict:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    ds_storage = await factory.open(dataset_id, org_id=org.id)
    if not ds_storage.capabilities.can_similarity:
        raise HTTPException(
            status_code=409,
            detail="Feature extraction is not supported for this dataset's storage mode",
        )

    embed_model: str = (dataset.embed_config or {}).get(
        "model", "openai/clip-vit-base-patch32"
    )
    from app.shared.api.schemas import PredictionJob

    job = PredictionJob(
        dataset_id=dataset_id,
        model_id="embedding-worker",
        created_by=current_user.id,
        target="embedding",
        org_id=org.id,
        model_version="force" if force else None,
        summary={"embed_model": embed_model},
    )
    if str(cfg.app.env) == "test":
        from app.shared.api.schemas import JobStatus

        samples, total = await repo.list_samples(dataset_id, limit=100_000)
        result = await feature_ops.extract_features(
            samples=samples,
            embed_model=embed_model,
            force=force,
            storage=storage,
        )
        job.status = JobStatus.COMPLETED
        job.summary = {
            "status": result.get("status", "completed"),
            "total_samples": total,
            "processed": result.get("computed", 0),
            "skipped": result.get("skipped", 0),
            "embedding_model": result.get("embedding_model", embed_model),
        }
        persisted = await repo.create_prediction_job(job, org_id=org.id)
        return _prediction_job_to_response(persisted).model_dump()
    try:
        started = await prediction_orchestrator.start_job(job)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to start feature extraction: {exc}"
        )
    return _prediction_job_to_response(started).model_dump()


@router.get(
    "/datasets/{dataset_id}/latest-predictions",
    response_model=list[PredictionResultResponse],
)
async def list_latest_predictions(
    dataset_id: str,
    batch_svc: BatchPredictionServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    repo: SqlRepositoryDep,
) -> list[PredictionResultResponse]:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return await batch_svc.get_latest_predictions(
        dataset_id, storage_mode=dataset.storage_mode
    )
