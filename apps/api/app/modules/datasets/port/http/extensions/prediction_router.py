from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.prediction.port.http.deps import (
    DatasetReaderDep,
)
from app.modules.datasets.port.http.deps import get_dataset_storage_factory
from app.modules.prediction.port.http.schemas import PredictionResultResponse
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.api.schemas import Organization, User

router = APIRouter(prefix="/api/v1", tags=["datasets"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentOrgDep = Annotated[Organization, Depends(get_current_org)]


def _prediction_result_to_response(result) -> PredictionResultResponse:
    return PredictionResultResponse(
        id=getattr(result, "id", None),
        sample_id=result.sample_id,
        predicted_label=result.predicted_label,
        confidence=result.confidence,
        model_id=result.model_id,
        target=result.target,
        model_version=result.model_version,
        job_id=result.job_id,
        created_at=getattr(result, "created_at", None),
        error=result.error,
    )


@router.get(
    "/datasets/{dataset_id}/latest-predictions",
    response_model=list[PredictionResultResponse],
)
async def list_latest_predictions(
    dataset_id: str,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
    dataset_reader: DatasetReaderDep,
    storage_factory: Annotated[
        DatasetStorageFactoryPort, Depends(get_dataset_storage_factory)
    ],
    offset: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1, le=10_000),
) -> list[PredictionResultResponse]:
    dataset = await dataset_reader.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    storage = await storage_factory.open(dataset_id, org.id)
    predictions = await storage.list_predictions(
        offset=offset,
        limit=limit,
        latest_per_sample=True,
    )
    return [_prediction_result_to_response(prediction) for prediction in predictions]
