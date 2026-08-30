from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.modules.auth.port.http.deps import get_current_org, get_current_user
from app.modules.dataset_collections.domain.errors import (
    DatasetCollectionConflictError,
    DatasetCollectionNotFoundError,
    DatasetCollectionPermissionError,
    DatasetCollectionValidationError,
)
from app.modules.dataset_collections.domain.repository import (
    CollectionSortField,
    SortDirection,
)
from app.modules.dataset_collections.port.http.deps import (
    CollectionModelManagementDep,
    CollectionRevisionPublishingDep,
    DatasetCollectionServiceDep,
)
from app.modules.dataset_collections.port.http.schemas import (
    CollectionPredictionBatchResponse,
    CollectionPredictionCoverageResponse,
    CreateCollectionPredictionBatchRequest,
    CreateDatasetCollectionRequest,
    CreateDatasetCollectionRevisionRequest,
    DatasetCollectionMemberResponse,
    DatasetCollectionMembershipResponse,
    DatasetCollectionResponse,
    DatasetCollectionRevisionResponse,
    LinkDatasetCollectionMembersRequest,
    ReplaceDatasetCollectionMembersRequest,
    UpdateCollectionDefaultModelRequest,
    UpdateDatasetCollectionRequest,
)
from app.shared.api.schemas import CreatorSummary, Organization, PaginatedResponse, User

router = APIRouter(prefix="/api/v1/dataset-collections", tags=["dataset-collections"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DatasetCollectionNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, DatasetCollectionPermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, DatasetCollectionConflictError):
        return HTTPException(
            status_code=409, detail={"code": exc.code, "detail": str(exc)}
        )
    if isinstance(exc, DatasetCollectionValidationError):
        status = 409 if exc.code == "dataset_already_linked" else 422
        return HTTPException(
            status_code=status, detail={"code": exc.code, "detail": str(exc)}
        )
    return HTTPException(status_code=500, detail="Unexpected collection error")


@router.post("", response_model=DatasetCollectionResponse)
async def create_collection(
    payload: CreateDatasetCollectionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
) -> DatasetCollectionResponse:
    try:
        collection = await service.create_collection(
            org_id=org.id,
            created_by=current_user.id,
            name=payload.name,
            description=payload.description,
            target_view_id=payload.target_view_id,
            duplicate_policy=payload.duplicate_policy,
            missing_data_policy=payload.missing_data_policy,
        )
    except (DatasetCollectionValidationError,) as exc:
        raise _http_error(exc) from exc
    return DatasetCollectionResponse.from_domain(collection)


@router.get("", response_model=PaginatedResponse[DatasetCollectionResponse])
async def list_collections(
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    creator_id: str | None = Query(default=None, max_length=255),
    q: str | None = Query(default=None, max_length=200),
    sort_by: CollectionSortField = Query(default="updated_at"),
    sort_order: SortDirection = Query(default="desc"),
) -> PaginatedResponse[DatasetCollectionResponse]:
    collections, total = await service.list_collections(
        org.id,
        offset=offset,
        limit=limit,
        creator_id=creator_id,
        query=q,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse(
        items=[DatasetCollectionResponse.from_domain(item) for item in collections],
        total=total,
    )


@router.get("/creators", response_model=list[CreatorSummary])
async def list_collection_creators(
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
) -> list[CreatorSummary]:
    del current_user
    return await service.list_collection_creators(org.id)


@router.get("/{collection_id}", response_model=DatasetCollectionResponse)
async def get_collection(
    collection_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
) -> DatasetCollectionResponse:
    del current_user
    try:
        collection = await service.get_collection(collection_id, org.id)
    except DatasetCollectionNotFoundError as exc:
        raise _http_error(exc) from exc
    return DatasetCollectionResponse.from_domain(collection)


@router.patch("/{collection_id}", response_model=DatasetCollectionResponse)
async def update_collection(
    collection_id: str,
    payload: UpdateDatasetCollectionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
) -> DatasetCollectionResponse:
    try:
        collection = await service.update_collection(
            collection_id,
            org.id,
            actor_id=current_user.id,
            name=payload.name,
            description=payload.description,
        )
    except (
        DatasetCollectionConflictError,
        DatasetCollectionNotFoundError,
        DatasetCollectionPermissionError,
    ) as exc:
        raise _http_error(exc) from exc
    return DatasetCollectionResponse.from_domain(collection)


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
) -> Response:
    try:
        await service.delete_collection(collection_id, org.id, actor_id=current_user.id)
    except (DatasetCollectionNotFoundError, DatasetCollectionPermissionError) as exc:
        raise _http_error(exc) from exc
    return Response(status_code=204)


@router.get(
    "/{collection_id}/members",
    response_model=list[DatasetCollectionMemberResponse],
)
async def list_members(
    collection_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
) -> list[DatasetCollectionMemberResponse]:
    del current_user
    try:
        members = await service.list_members(collection_id, org.id)
    except DatasetCollectionNotFoundError as exc:
        raise _http_error(exc) from exc
    return [DatasetCollectionMemberResponse.from_domain(item) for item in members]


@router.post(
    "/{collection_id}/members",
    response_model=DatasetCollectionMembershipResponse,
)
async def link_members(
    collection_id: str,
    payload: LinkDatasetCollectionMembersRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
) -> DatasetCollectionMembershipResponse:
    try:
        collection, members = await service.link_members(
            collection_id,
            org.id,
            actor_id=current_user.id,
            expected_definition_version=payload.expected_definition_version,
            members=tuple(item.to_domain() for item in payload.members),
        )
    except (
        DatasetCollectionConflictError,
        DatasetCollectionNotFoundError,
        DatasetCollectionPermissionError,
        DatasetCollectionValidationError,
    ) as exc:
        raise _http_error(exc) from exc
    return DatasetCollectionMembershipResponse.from_domain(collection, members)


@router.put(
    "/{collection_id}/members",
    response_model=DatasetCollectionMembershipResponse,
)
async def replace_members(
    collection_id: str,
    payload: ReplaceDatasetCollectionMembersRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
) -> DatasetCollectionMembershipResponse:
    try:
        collection, members = await service.replace_members(
            collection_id,
            org.id,
            actor_id=current_user.id,
            expected_definition_version=payload.expected_definition_version,
            members=tuple(item.to_domain() for item in payload.members),
        )
    except (
        DatasetCollectionConflictError,
        DatasetCollectionNotFoundError,
        DatasetCollectionPermissionError,
        DatasetCollectionValidationError,
    ) as exc:
        raise _http_error(exc) from exc
    return DatasetCollectionMembershipResponse.from_domain(collection, members)


@router.delete(
    "/{collection_id}/members/{member_id}",
    response_model=DatasetCollectionMembershipResponse,
)
async def unlink_member(
    collection_id: str,
    member_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
    expected_definition_version: int = Query(ge=0),
) -> DatasetCollectionMembershipResponse:
    try:
        collection, members = await service.unlink_member(
            collection_id,
            member_id,
            org.id,
            actor_id=current_user.id,
            expected_definition_version=expected_definition_version,
        )
    except (
        DatasetCollectionConflictError,
        DatasetCollectionNotFoundError,
        DatasetCollectionPermissionError,
    ) as exc:
        raise _http_error(exc) from exc
    return DatasetCollectionMembershipResponse.from_domain(collection, members)


@router.patch(
    "/{collection_id}/default-model",
    response_model=DatasetCollectionResponse,
)
async def update_default_model(
    collection_id: str,
    payload: UpdateCollectionDefaultModelRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: CollectionModelManagementDep,
) -> DatasetCollectionResponse:
    try:
        collection = await service.set_default_model(
            collection_id,
            org.id,
            actor_id=current_user.id,
            expected_binding_version=payload.expected_binding_version,
            model_id=payload.model_id,
        )
    except (
        DatasetCollectionConflictError,
        DatasetCollectionNotFoundError,
        DatasetCollectionPermissionError,
        DatasetCollectionValidationError,
    ) as exc:
        raise _http_error(exc) from exc
    return DatasetCollectionResponse.from_domain(collection)


@router.get(
    "/{collection_id}/prediction-coverage",
    response_model=list[CollectionPredictionCoverageResponse],
)
async def list_prediction_coverage(
    collection_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: CollectionModelManagementDep,
    revision_id: str | None = Query(default=None, min_length=1, max_length=64),
) -> list[CollectionPredictionCoverageResponse]:
    del current_user
    try:
        coverage = await service.list_coverage(
            collection_id, org.id, revision_id=revision_id
        )
    except (DatasetCollectionNotFoundError, DatasetCollectionValidationError) as exc:
        raise _http_error(exc) from exc
    return [CollectionPredictionCoverageResponse.from_domain(item) for item in coverage]


@router.post(
    "/{collection_id}/prediction-batches",
    response_model=CollectionPredictionBatchResponse,
)
async def create_prediction_batch(
    collection_id: str,
    payload: CreateCollectionPredictionBatchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: CollectionModelManagementDep,
) -> CollectionPredictionBatchResponse:
    try:
        batch, items = await service.create_reconciliation_batch(
            collection_id,
            org.id,
            actor_id=current_user.id,
            revision_id=payload.revision_id,
            expected_default_model_id=payload.expected_default_model_id,
            request_id=payload.request_id,
            dataset_ids=tuple(payload.dataset_ids),
        )
    except (
        DatasetCollectionConflictError,
        DatasetCollectionNotFoundError,
        DatasetCollectionPermissionError,
        DatasetCollectionValidationError,
    ) as exc:
        raise _http_error(exc) from exc
    return CollectionPredictionBatchResponse.from_domain(batch, items)


@router.get(
    "/{collection_id}/prediction-batches",
    response_model=list[CollectionPredictionBatchResponse],
)
async def list_prediction_batches(
    collection_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: CollectionModelManagementDep,
) -> list[CollectionPredictionBatchResponse]:
    del current_user
    try:
        batches = await service.list_batches(collection_id, org.id)
    except DatasetCollectionNotFoundError as exc:
        raise _http_error(exc) from exc
    return [
        CollectionPredictionBatchResponse.from_domain(batch, items)
        for batch, items in batches
    ]


@router.post(
    "/{collection_id}/prediction-batches/{batch_id}/retry",
    response_model=CollectionPredictionBatchResponse,
)
async def retry_prediction_batch(
    collection_id: str,
    batch_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: CollectionModelManagementDep,
) -> CollectionPredictionBatchResponse:
    try:
        batch, items = await service.retry_batch(
            batch_id,
            org.id,
            actor_id=current_user.id,
        )
        if batch.collection_id != collection_id:
            raise DatasetCollectionNotFoundError(
                "Collection prediction batch not found"
            )
    except (
        DatasetCollectionNotFoundError,
        DatasetCollectionPermissionError,
        DatasetCollectionValidationError,
    ) as exc:
        raise _http_error(exc) from exc
    return CollectionPredictionBatchResponse.from_domain(batch, items)


@router.post(
    "/{collection_id}/revisions",
    response_model=DatasetCollectionRevisionResponse,
)
async def create_revision(
    collection_id: str,
    payload: CreateDatasetCollectionRevisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: CollectionRevisionPublishingDep,
) -> DatasetCollectionRevisionResponse:
    try:
        revision = await service.create_revision(
            collection_id,
            org.id,
            actor_id=current_user.id,
            expected_definition_version=payload.expected_definition_version,
            trigger_kind="manual",
            trigger_ref=None,
        )
    except (
        DatasetCollectionConflictError,
        DatasetCollectionNotFoundError,
        DatasetCollectionPermissionError,
        DatasetCollectionValidationError,
    ) as exc:
        raise _http_error(exc) from exc
    return DatasetCollectionRevisionResponse.from_domain(revision)


@router.get(
    "/{collection_id}/revisions",
    response_model=list[DatasetCollectionRevisionResponse],
)
async def list_revisions(
    collection_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
) -> list[DatasetCollectionRevisionResponse]:
    del current_user
    try:
        revisions = await service.list_revisions(collection_id, org.id)
    except DatasetCollectionNotFoundError as exc:
        raise _http_error(exc) from exc
    return [DatasetCollectionRevisionResponse.from_domain(item) for item in revisions]


@router.get(
    "/{collection_id}/revisions/{revision_id}",
    response_model=DatasetCollectionRevisionResponse,
)
async def get_revision(
    collection_id: str,
    revision_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    service: DatasetCollectionServiceDep,
) -> DatasetCollectionRevisionResponse:
    del current_user
    try:
        revision = await service.get_revision(collection_id, revision_id, org.id)
    except DatasetCollectionNotFoundError as exc:
        raise _http_error(exc) from exc
    return DatasetCollectionRevisionResponse.from_domain(revision)
