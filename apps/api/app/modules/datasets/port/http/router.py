from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse

from app.modules.datasets.port.http.deps import (
    ArtifactLookupRepositoryDep,
    DatasetDeletionGuardDep,
    DatasetRevisionReaderDep,
    DatasetServiceDep,
    LabelStudioClientDep,
    RedisEventPublisherDep,
    SampleSimilarityDep,
    SessionFactoryDep,
    get_artifact_storage,
    get_dataset_payload_store,
    get_dataset_storage_factory,
    get_repository,
)
from app.modules.datasets.app.services.dataset_deletion_guard import (
    DatasetDeletionConflictError,
)
from app.modules.datasets.app.services.dataset_revision_service import (
    DatasetNotFoundError,
    DatasetRevisionNotFoundError,
)
from app.modules.datasets.domain.repository import DatasetSortField, SortDirection
from app.modules.storage.adapter.factory import DatasetStorageFactory
from app.modules.datasets.domain.sample_row import BulkSampleRow
from app.modules.storage.domain.storage_agg import DatasetStorageAgg
from app.shared.api.schemas import (
    DatasetAnnotationStats,
    PaginatedResponse,
    SetPublicRequest,
    SetPublicResponse,
)
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.storage.domain.sparse import SparseManifestReader
from app.modules.datasets.port.http.schemas import (
    BulkAnnotationRequest,
    BulkAnnotationResponse,
    BulkCreateSampleRequest,
    BulkCreateSampleResponse,
    CreateAnnotationRequest,
    CreateDatasetRequest,
    DatasetRevisionResponse,
    DatasetStatusResponse,
    CreateSampleRequest,
    LatestAnnotation,
    PersistExportResponse,
    SampleWithLabels,
    SimilarityResponse,
    SparseManifestSummary,
    SparseShardSummary,
    SparseSummaryResponse,
    SyncAnnotationsResponse,
    UpdateAnnotationRequest,
    UpdateDatasetRequest,
    UpdateLabelSpaceRequest,
    UpdateSampleImageResponse,
    ViewPaginatedResponse,
    SparseSummaryJsonScalar,
    SparseSummaryJsonValue,
)
from app.modules.datasets.views.deps import DatasetSessionFactoryDep
from app.shared.api.schemas import (
    Annotation,
    CreatorSummary,
    Dataset,
    Organization,
    Sample,
    SPARSE_NO_LS,
    User,
)
from app.shared.domain.protocols import ArtifactStorage
from app.shared.api.schemas import DatasetStorageMode
from app.modules.storage.domain.sparse import DatasetManifest, DatasetPayloadStore
from app.modules.datasets.app.services.sparse_export import SparseExportAssembler
from app.shared.application.artifacts import ArtifactService
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.prediction.port.http.deps import (
    get_artifact_service,
)
from app.shared.api.utils import _infer_dataset_type, _make_ls_image_url
from app.shared.infrastructure.label_studio.client import (
    LabelStudioNotFoundError,
    platform_annotation_to_ls,
)
from app.shared.infrastructure.label_studio.read_repository import LsReadRepository
from app.shared.sse.emit import emit_sse
from app.shared.sse.events import (
    DoneEvent,
    ScDataEvent,
    ScErrorEvent,
    ScProgressEvent,
    SSEEvent,
)


def _create_ls_read_repository() -> LsReadRepository:
    from app.core.config import load_config
    from app.shared.infrastructure.label_studio.session import (
        create_ls_engine,
        create_ls_session_factory,
    )

    cfg = load_config()
    engine = create_ls_engine(database_url=str(cfg.label_studio.database_url))
    return LsReadRepository(session_factory=create_ls_session_factory(engine=engine))


LsReadRepositoryFactory = Callable[[], LsReadRepository]


def get_ls_read_repository_factory() -> LsReadRepositoryFactory:
    """Return a lazy LS reader factory for DB_FULL export requests."""
    return _create_ls_read_repository


def _open_ls_read_repository(
    factory: LsReadRepositoryFactory,
) -> LsReadRepository:
    try:
        return factory()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Label Studio database configuration failed: {exc}",
        ) from exc


router = APIRouter(prefix="/api/v1", tags=["datasets"])
_logger = logging.getLogger(__name__)
_MAX_SAMPLE_UPLOAD_BYTES = 10 * 1024 * 1024
_ANNOTATION_SYNC_PAGE_SIZE = 1000
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

DatasetStorageFactoryDep = Annotated[
    DatasetStorageFactory, Depends(get_dataset_storage_factory)
]


async def _open_storage(
    factory: DatasetStorageFactory, dataset_id: str, org_id: str
) -> DatasetStorageAgg:
    try:
        return await factory.open(dataset_id, org_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Dataset not found")


def _to_sparse_summary_scalar(value: object) -> SparseSummaryJsonScalar:
    if isinstance(value, bytes | bytearray | memoryview):
        return "<binary omitted>"
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _to_sparse_summary_json(value: object) -> SparseSummaryJsonValue:
    if isinstance(value, dict):
        return {
            str(k): _to_sparse_summary_scalar(v)
            for k, v in value.items()
            if k not in {"bytes", "source_uri"}
        }
    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            return [
                {
                    str(k): _to_sparse_summary_scalar(v)
                    for k, v in item.items()
                    if k not in {"bytes", "source_uri"}
                }
                for item in value
                if isinstance(item, dict)
            ]
        return [_to_sparse_summary_scalar(v) for v in value]
    if isinstance(value, tuple):
        return [_to_sparse_summary_scalar(v) for v in value]
    return _to_sparse_summary_scalar(value)


# ---------------------------------------------------------------------------
# Dataset CRUD
# ---------------------------------------------------------------------------


@router.post("/datasets", response_model=Dataset)
async def create_dataset(
    payload: CreateDatasetRequest,
    service: DatasetServiceDep,
    ls_client: LabelStudioClientDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> Dataset:
    dataset_type = payload.dataset_type or _infer_dataset_type(
        payload.task_spec.task_type
    )
    try:
        from app.shared.application.compatibility import validate_dataset_contract

        validate_dataset_contract(
            dataset_type, payload.task_spec.task_type, payload.task_spec.label_space
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from app.core.registry import resolve_view_types

    view_types = resolve_view_types(dataset_type)

    if payload.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
        ls_project_id = SPARSE_NO_LS
    else:
        # LS-first: create project, fail if LS fails
        try:
            from app.shared.infrastructure.label_studio.client import (
                LabelStudioClient as _LSC,
            )

            label_config = _LSC.generate_image_classification_config(
                payload.task_spec.label_space
            )
            project = await ls_client.create_project(payload.name, label_config)
            ls_project_id = str(project.get("id", ""))
            if not ls_project_id:
                raise HTTPException(
                    status_code=502,
                    detail="Label Studio project creation returned no ID.",
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Label Studio project creation failed: {exc}"
            )
    dataset = Dataset(
        name=payload.name,
        dataset_type=dataset_type,
        view_types=view_types,
        task_spec=payload.task_spec,
        org_id=org.id,
        created_by=current_user.id,
        ls_project_id=ls_project_id,
        storage_mode=payload.storage_mode,
    )
    try:
        dataset = await repo.create_dataset(dataset)
    except Exception:
        if ls_project_id and ls_project_id != SPARSE_NO_LS:
            try:
                await ls_client.delete_project(int(ls_project_id))
            except Exception:
                _logger.warning(
                    "Failed to clean Label Studio project %s after dataset persistence error",
                    ls_project_id,
                    exc_info=True,
                )
        raise
    if payload.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
        manifest = DatasetManifest(
            dataset_id=dataset.id,
            storage_mode=dataset.storage_mode.value,
            shard_count=0,
            total_rows=0,
        )
        payload_store = DatasetPayloadStore(storage)
        try:
            await payload_store.put_manifest(manifest, org_id=org.id)
        except Exception as exc:
            try:
                await payload_store.delete_dataset_payload(dataset.id, org.id)
            except Exception:
                _logger.warning(
                    "Failed to clean sparse payload for dataset %s after initialization error",
                    dataset.id,
                    exc_info=True,
                )
            try:
                await repo.delete_dataset(dataset.id, org_id=org.id)
            except Exception:
                _logger.warning(
                    "Failed to roll back dataset %s after sparse initialization error",
                    dataset.id,
                    exc_info=True,
                )
            raise HTTPException(
                status_code=502,
                detail=f"Failed to initialize sparse dataset storage: {exc}",
            ) from exc
    return service.to_response(dataset)


@router.get("/datasets", response_model=PaginatedResponse[Dataset])
async def list_datasets(
    service: DatasetServiceDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    creator_id: str | None = Query(default=None, max_length=255),
    sort_by: DatasetSortField = Query(default="created_at"),
    sort_order: SortDirection = Query(default="desc"),
) -> PaginatedResponse[Dataset]:
    datasets = await repo.list_datasets(
        org_id=org.id,
        limit=limit,
        offset=offset,
        query=q,
        creator_id=creator_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = await repo.count_datasets(
        org_id=org.id,
        query=q,
        creator_id=creator_id,
    )
    items = [service.to_response(dataset) for dataset in datasets]
    return PaginatedResponse(items=items, total=total)


@router.get("/datasets/creators", response_model=list[CreatorSummary])
async def list_dataset_creators(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
) -> list[CreatorSummary]:
    return await repo.list_dataset_creators(org_id=org.id)


@router.get("/datasets/{dataset_id}", response_model=Dataset)
async def get_dataset(
    dataset_id: str,
    service: DatasetServiceDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
) -> Dataset:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return service.to_response(dataset)


@router.get(
    "/datasets/{dataset_id}/revisions/current",
    response_model=DatasetRevisionResponse,
)
async def get_current_dataset_revision(
    dataset_id: str,
    revisions: DatasetRevisionReaderDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> DatasetRevisionResponse:
    try:
        revision = await revisions.get_current(dataset_id, org.id)
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found")
    except DatasetRevisionNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset revision not found")
    return DatasetRevisionResponse.from_domain(revision)


@router.get(
    "/datasets/{dataset_id}/revisions",
    response_model=PaginatedResponse[DatasetRevisionResponse],
)
async def list_dataset_revisions(
    dataset_id: str,
    revisions: DatasetRevisionReaderDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[DatasetRevisionResponse]:
    try:
        items, total = await revisions.list_history(
            dataset_id,
            org.id,
            limit=limit,
            offset=offset,
        )
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return PaginatedResponse(
        items=[DatasetRevisionResponse.from_domain(item) for item in items],
        total=total,
    )


@router.get(
    "/datasets/{dataset_id}/sparse-summary",
    response_model=SparseSummaryResponse,
)
async def get_sparse_summary(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> SparseSummaryResponse:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if dataset.storage_mode != DatasetStorageMode.FILE_SHARD_SPARSE:
        raise HTTPException(
            status_code=409,
            detail="This endpoint is for file_shard_sparse datasets only",
        )

    store = DatasetPayloadStore(storage)
    try:
        manifest = await store.get_manifest(dataset_id, org.id)
    except (FileNotFoundError, KeyError):
        raise HTTPException(
            status_code=404,
            detail="Dataset manifest not found — dataset payload may not be initialized",
        )

    reader = SparseManifestReader()
    sample_rows: list[dict[str, SparseSummaryJsonValue]] = []
    if manifest.shards:
        first_shard = manifest.shards[0]
        raw_rows = await reader.read_row_batch(
            first_shard.uri,
            0,
            min(5, first_shard.row_count),
            storage,
        )
        rows: list[dict[str, SparseSummaryJsonValue]] = []
        for raw_row in raw_rows:
            rows.append(
                {
                    str(k): _to_sparse_summary_json(v)
                    for k, v in raw_row.items()
                    if k not in {"bytes", "source_uri"}
                }
            )
        sample_rows = rows

    return SparseSummaryResponse(
        dataset_id=dataset.id,
        name=dataset.name,
        dataset_type=dataset.dataset_type,
        storage_mode=dataset.storage_mode.value,
        manifest=SparseManifestSummary(
            shard_count=manifest.shard_count,
            total_rows=manifest.total_rows,
            schema_columns=[
                {"name": c.name, "type": c.type}
                for c in (manifest.schema_columns or [])
            ],
            created_at=manifest.created_at.isoformat(),
        ),
        shards=[
            SparseShardSummary(
                shard_index=s.shard_index,
                row_count=s.row_count,
                format=s.format,
                byte_size=s.byte_size,
            )
            for s in manifest.shards
        ],
        sample_rows=sample_rows,
    )


@router.delete("/datasets/{dataset_id}", status_code=204)
async def delete_dataset(
    dataset_id: str,
    deletion_guard: DatasetDeletionGuardDep,
    ls_client: LabelStudioClientDep,
    factory: DatasetStorageFactoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
) -> Response:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.org_id != org.id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.created_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the dataset creator can delete this dataset",
        )

    try:
        await deletion_guard.ensure_deletable(dataset_id=dataset_id, org_id=org.id)
    except DatasetDeletionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if dataset.ls_project_id and dataset.ls_project_id != SPARSE_NO_LS:
        try:
            await ls_client.delete_project(int(dataset.ls_project_id))
        except LabelStudioNotFoundError:
            pass
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to delete Label Studio project: {exc}",
            ) from exc

    dataset_storage = await _open_storage(factory, dataset_id, org_id=org.id)
    await dataset_storage.delete()
    return Response(status_code=204)


@router.patch("/datasets/{dataset_id}", response_model=Dataset)
async def update_dataset(
    dataset_id: str,
    payload: UpdateDatasetRequest,
    service: DatasetServiceDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
) -> Dataset:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.org_id != org.id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.created_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the dataset creator can rename this dataset",
        )
    updated = await repo.rename_dataset(dataset_id, name=payload.name, org_id=org.id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return service.to_response(updated)


@router.patch("/datasets/{dataset_id}/label-space", response_model=Dataset)
async def update_label_space(
    dataset_id: str,
    payload: UpdateLabelSpaceRequest,
    service: DatasetServiceDep,
    ls_client: LabelStudioClientDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
) -> Dataset:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.created_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the dataset creator can update its label space",
        )
    try:
        from app.shared.application.compatibility import validate_dataset_contract

        validate_dataset_contract(
            dataset.dataset_type,
            dataset.task_spec.task_type,
            payload.label_space,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Update Label Studio project config with new labels
    label_studio_updated = False
    ls_project_id = dataset.ls_project_id
    if ls_project_id and ls_project_id != SPARSE_NO_LS:
        try:
            from app.shared.infrastructure.label_studio.client import (
                LabelStudioClient as _LSC,
            )

            label_config = _LSC.generate_image_classification_config(
                payload.label_space
            )
            await ls_client.update_project(
                int(ls_project_id), label_config=label_config
            )
            label_studio_updated = True
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Failed to update Label Studio project: {exc}"
            )

    new_task_spec = dataset.task_spec.model_dump()
    new_task_spec["label_space"] = payload.label_space
    try:
        updated = await repo.update_dataset_meta(
            dataset_id,
            new_task_spec,
            org_id=org.id,
        )
    except Exception:
        if label_studio_updated:
            try:
                assert ls_project_id is not None
                from app.shared.infrastructure.label_studio.client import (
                    LabelStudioClient as _LSC,
                )

                previous_config = _LSC.generate_image_classification_config(
                    dataset.task_spec.label_space
                )
                await ls_client.update_project(
                    int(ls_project_id),
                    label_config=previous_config,
                )
            except Exception:
                _logger.warning(
                    "Failed to restore Label Studio labels for dataset %s",
                    dataset_id,
                    exc_info=True,
                )
        raise
    if updated is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return service.to_response(updated)


@router.patch("/datasets/{dataset_id}/public", response_model=SetPublicResponse)
async def set_dataset_public(
    dataset_id: str,
    _payload: SetPublicRequest,
    _current_user: User = Depends(get_current_user),
) -> SetPublicResponse:
    raise HTTPException(status_code=410, detail="Make Public is disabled")


# ---------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------


async def _collect_bulk_rows(rows: list[BulkSampleRow]) -> AsyncIterator[BulkSampleRow]:
    for row in rows:
        yield row


@router.post("/datasets/{dataset_id}/samples", response_model=Sample)
async def create_sample(
    dataset_id: str,
    payload: CreateSampleRequest,
    ls_client: LabelStudioClientDep,
    factory: DatasetStorageFactoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
) -> Sample:
    storage = await _open_storage(factory, dataset_id, org_id=org.id)
    if not storage.dataset_id:
        raise HTTPException(status_code=404, detail="dataset not found")
    if storage.storage_mode != DatasetStorageMode.DB_FULL:
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot create sample.",
        )
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if not dataset.ls_project_id or dataset.ls_project_id == SPARSE_NO_LS:
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot create sample.",
        )
    try:
        image_url = (
            _make_ls_image_url(payload.image_uris[0]) if payload.image_uris else ""
        )
        task_data: dict[str, object] = {"image": image_url}
        task = await ls_client.create_task(int(dataset.ls_project_id), task_data)
        ls_task_id_raw = task.get("id")
        if ls_task_id_raw is None:
            raise HTTPException(
                status_code=502, detail="Label Studio task creation returned no ID."
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Label Studio task creation failed: {exc}"
        )
    sid = uuid4().hex
    ls_task_id = int(str(ls_task_id_raw))
    row = BulkSampleRow(
        sample_id=sid,
        image_uris=list(payload.image_uris),
        metadata=dict(payload.metadata),
        extra={"ls_task_id": ls_task_id},
    )
    await storage.write_samples(_collect_bulk_rows([row]))
    sample_row = await storage.get_sample(sid)
    if sample_row is None:
        raise HTTPException(status_code=500, detail="Sample not found after creation")
    return Sample(
        id=sample_row.sample_id,
        dataset_id=sample_row.dataset_id,
        image_uris=sample_row.image_uris,
        metadata=sample_row.metadata,
        ls_task_id=sample_row.ls_task_id,
    )


@router.post(
    "/datasets/{dataset_id}/samples/import",
    response_model=BulkCreateSampleResponse,
)
async def import_samples(
    dataset_id: str,
    payload: BulkCreateSampleRequest,
    ls_client: LabelStudioClientDep,
    dataset_service: DatasetServiceDep,
    factory: DatasetStorageFactoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
) -> BulkCreateSampleResponse:
    storage = await _open_storage(factory, dataset_id, org_id=org.id)
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if not dataset.ls_project_id or dataset.ls_project_id == SPARSE_NO_LS:
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot create sample.",
        )
    if not payload.items:
        return BulkCreateSampleResponse(dataset_id=dataset_id, imported=0, failed=0)

    ls_tasks: list[dict[str, object]] = []
    for item in payload.items:
        image_url = _make_ls_image_url(item.image_uris[0]) if item.image_uris else ""
        task_data: dict[str, object] = {"image": image_url}
        ls_tasks.append(task_data)

    try:
        imported = await ls_client.import_tasks(
            int(dataset.ls_project_id),
            ls_tasks,
            return_task_ids=True,
        )
        imported_dict: dict = imported if isinstance(imported, dict) else {}
        task_ids = [int(tid) for tid in imported_dict.get("task_ids", [])]
        if len(task_ids) != len(payload.items):
            raise HTTPException(
                status_code=502,
                detail="Label Studio bulk import returned mismatched task IDs.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Label Studio bulk import failed: {exc}"
        )

    sample_ids: list[str] = [uuid4().hex for _ in payload.items]
    bulk_rows = [
        BulkSampleRow(
            sample_id=sample_ids[idx],
            image_uris=list(item.image_uris),
            metadata=dict(item.metadata),
            label=item.label,
            extra={"ls_task_id": task_ids[idx]},
        )
        for idx, item in enumerate(payload.items)
    ]

    await storage.write_samples(_collect_bulk_rows(bulk_rows))

    ann_list: list[Annotation] = []
    for idx, item in enumerate(payload.items):
        if item.label is None:
            continue
        sid = sample_ids[idx]
        ls_tid = task_ids[idx]
        await ls_client.create_annotation(
            ls_tid,
            platform_annotation_to_ls(item.label),
        )
        ann_list.append(
            Annotation(
                sample_id=sid,
                label=item.label,
                created_by=current_user.email,
            )
        )
    if ann_list:
        await storage.create_annotations(ann_list)

    # ── Auto-expand label_space with newly introduced labels ──────────
    incoming_labels = {item.label for item in payload.items if item.label}
    if incoming_labels:
        await dataset_service.merge_label_space(dataset_id, org.id, incoming_labels)

    return BulkCreateSampleResponse(
        dataset_id=dataset_id,
        imported=len(sample_ids),
        failed=0,
        sample_ids=sample_ids,
        ls_task_ids=task_ids,
    )


@router.get("/datasets/{dataset_id}/samples", response_model=PaginatedResponse[Sample])
async def list_samples(
    dataset_id: str,
    factory: DatasetStorageFactoryDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PaginatedResponse[Sample]:
    storage = await _open_storage(factory, dataset_id, org_id=org.id)
    rows, total = await storage.list_samples(offset=offset, limit=limit)
    samples = [
        Sample(
            id=r.sample_id,
            dataset_id=r.dataset_id,
            image_uris=r.image_uris,
            metadata=r.metadata,
            ls_task_id=r.ls_task_id,
        )
        for r in rows
    ]
    return PaginatedResponse(items=samples, total=total)  # type: ignore[return-value]


@router.get(
    "/datasets/{dataset_id}/samples-with-labels",
    response_model=PaginatedResponse[SampleWithLabels],
)
async def list_samples_with_labels_endpoint(
    dataset_id: str,
    factory: DatasetStorageFactoryDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    label: str | None = None,
    order_by: str = "id",
    with_predictions: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PaginatedResponse[SampleWithLabels]:
    storage = await _open_storage(factory, dataset_id, org_id=org.id)
    rows, total = await storage.list_samples(
        offset=offset,
        limit=limit,
        with_labels=True,
        with_predictions=with_predictions,
        label_filter=label,
        order_by=order_by,
    )
    return PaginatedResponse(
        items=[
            SampleWithLabels(
                id=r.sample_id,
                dataset_id=r.dataset_id,
                image_uris=r.image_uris,
                metadata=r.metadata,
                ls_task_id=r.ls_task_id,
                latest_annotation=(
                    LatestAnnotation(
                        id=r.annotation_id or "",
                        label=r.latest_label or "",
                        created_by="",
                        created_at=r.created_at.isoformat() if r.created_at else "",
                    )
                    if r.latest_label is not None
                    else None
                ),
                latest_prediction=r.latest_prediction,
            )
            for r in rows
        ],
        total=total,
    )


@router.get(
    "/datasets/{dataset_id}/views/{view_type}/samples",
)
async def list_view_samples(
    dataset_id: str,
    view_type: str,
    session_factory: DatasetSessionFactoryDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    order_by: str = Query(default="id"),
    sampling_count: int | None = Query(default=None, ge=1),
    sample_ids: str | None = Query(default=None, alias="sampleIds"),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    session = await session_factory.create(dataset_id, view_type, org.id)
    requested_sample_ids = (
        [value for value in sample_ids.split(",") if value]
        if sample_ids is not None
        else None
    )
    if sampling_count is not None:
        items, total = await session.list_samples(
            view_type,
            offset=0,
            limit=sampling_count,
            order_by="random",
            sample_ids=requested_sample_ids,
        )
    else:
        items, total = await session.list_samples(
            view_type,
            offset,
            limit,
            order_by,
            sample_ids=requested_sample_ids,
        )

    return ViewPaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        view_type=view_type,
        dataset_id=dataset_id,
    )


@router.get(
    "/datasets/{dataset_id}/annotation-stats",
    response_model=DatasetAnnotationStats,
)
async def get_annotation_stats(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    factory: DatasetStorageFactory = Depends(get_dataset_storage_factory),
) -> DatasetAnnotationStats:
    storage = await _open_storage(factory, dataset_id, org.id)
    stats = await storage.get_annotation_stats()
    return DatasetAnnotationStats(**stats)


@router.get(
    "/datasets/{dataset_id}/status",
    response_model=DatasetStatusResponse,
)
async def get_dataset_status(
    dataset_id: str,
    service: DatasetServiceDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> DatasetStatusResponse:
    status = await service.get_status(dataset_id, org.id)
    return DatasetStatusResponse(
        allow_train=status.allow_train,
        train_disabled_reason=status.train_disabled_reason,
        minimum_active_class_count=status.minimum_active_class_count,
        active_class_count=status.active_class_count,
        annotated_samples=status.annotated_samples,
        total_samples=status.total_samples,
    )


@router.get("/datasets/{dataset_id}/samples/{sample_id}", response_model=Sample)
async def get_sample(
    dataset_id: str,
    sample_id: str,
    factory: DatasetStorageFactoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Sample:
    storage = await _open_storage(factory, dataset_id, org_id=org.id)
    sample_row = await storage.get_sample(sample_id)
    if sample_row is None:
        raise HTTPException(status_code=404, detail="sample not found")
    return Sample(
        id=sample_row.sample_id,
        dataset_id=sample_row.dataset_id,
        image_uris=sample_row.image_uris,
        metadata=sample_row.metadata,
        ls_task_id=sample_row.ls_task_id,
    )


@router.post(
    "/datasets/{dataset_id}/samples/{sample_id}/upload",
    response_model=UpdateSampleImageResponse,
)
async def upload_sample_image(
    dataset_id: str,
    sample_id: str,
    factory: DatasetStorageFactoryDep,
    storage: ArtifactStorage = Depends(get_artifact_storage),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> UpdateSampleImageResponse:
    dataset_storage = await _open_storage(factory, dataset_id, org_id=org.id)
    if dataset_storage.storage_mode != DatasetStorageMode.DB_FULL:
        raise HTTPException(
            status_code=400,
            detail="Image upload is only supported for db_full datasets.",
        )

    sample_row = await dataset_storage.get_sample(sample_id)
    if sample_row is None:
        raise HTTPException(status_code=404, detail="sample not found")

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    data = await file.read()
    if len(data) > _MAX_SAMPLE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    safe_name = (file.filename or "upload").replace("/", "_").replace("\\", "_")
    object_name = (
        f"datasets/{org.id}/{dataset_id}/samples/{sample_id}/{uuid4().hex}-{safe_name}"
    )
    uri = await storage.put_bytes(object_name, data, content_type=content_type)
    next_image_uris = [*sample_row.image_uris, uri]
    updated = await dataset_storage.update_sample_image_uris(sample_id, next_image_uris)
    if updated is None:
        raise HTTPException(status_code=404, detail="sample not found")

    return UpdateSampleImageResponse(
        uri=uri,
        sample_id=sample_id,
        index=len(next_image_uris) - 1,
    )


@router.get(
    "/datasets/{dataset_id}/samples/{sample_id}/images/{image_id}",
    response_class=Response,
)
async def serve_sparse_sample_image(
    dataset_id: str,
    sample_id: str,
    image_id: str,
    storage: ArtifactStorage = Depends(get_artifact_storage),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    """Serve an image embedded in a v2 sparse shard.

    Reads the shard row identified by *sample_id* within *dataset_id*,
    extracts the image struct matching *image_id* from the ``images``
    list<struct> column, and returns the raw bytes with the correct
    Content-Type header.
    """
    store = DatasetPayloadStore(storage)
    reader = SparseManifestReader()

    try:
        manifest = await store.get_manifest(dataset_id, org.id)
    except (FileNotFoundError, KeyError):
        raise HTTPException(
            status_code=404,
            detail=f"Dataset not found or has no manifest: {dataset_id}",
        )

    locator = (await store.lookup_sample_locators(manifest, [sample_id])).get(sample_id)
    if locator is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sample not found in dataset {dataset_id}: {sample_id}",
        )

    if locator.shard_index < 0 or locator.shard_index >= len(manifest.shards):
        raise HTTPException(
            status_code=404,
            detail=f"Shard index out of range for sample {sample_id}",
        )

    shard = manifest.shards[locator.shard_index]
    if locator.row_index < 0 or locator.row_index >= shard.row_count:
        raise HTTPException(
            status_code=404,
            detail=f"Row index out of range for sample {sample_id}",
        )

    try:
        rows = await reader.read_row_batch(
            shard.uri, locator.row_index, 1, storage, columns=["images"]
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read shard row: {exc}",
        )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Sample row not found in shard: {sample_id}",
        )

    images_raw = rows[0].get("images")
    if images_raw is None:
        raise HTTPException(
            status_code=404,
            detail=f"No images column for sample: {sample_id}",
        )

    images_list: list[dict[str, object]] = []
    if isinstance(images_raw, list):
        images_list = [dict(img) if isinstance(img, dict) else {} for img in images_raw]

    matched: dict[str, object] | None = None
    for img in images_list:
        if str(img.get("image_id", "")) == image_id:
            matched = img
            break

    if matched is None:
        raise HTTPException(
            status_code=404,
            detail=f"Image {image_id} not found in sample {sample_id}",
        )

    raw_bytes = matched.get("bytes")
    if not isinstance(raw_bytes, bytes):
        raise HTTPException(
            status_code=500,
            detail=f"Invalid or missing image bytes for image {image_id}",
        )

    content_type = str(matched.get("content_type", ""))
    if not content_type or "/" not in content_type:
        content_type = "application/octet-stream"

    filename = str(matched.get("filename", f"{sample_id}_{image_id}"))

    return Response(
        content=raw_bytes,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=1200",
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


@router.post("/annotations", response_model=Annotation)
async def create_annotation(
    payload: CreateAnnotationRequest,
    ls_client: LabelStudioClientDep,
    dataset_service: DatasetServiceDep,
    factory: DatasetStorageFactoryDep,
    event_publisher: RedisEventPublisherDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Annotation:
    storage = await _open_storage(factory, payload.dataset_id, org_id=org.id)
    sample_row = await storage.get_sample(payload.sample_id)
    if sample_row is None:
        raise HTTPException(status_code=404, detail="sample not found")
    if not sample_row.ls_task_id:
        raise HTTPException(
            status_code=500,
            detail="Sample has no Label Studio task — cannot create annotation.",
        )
    try:
        from app.shared.infrastructure.label_studio.client import (
            platform_annotation_to_ls,
        )

        ls_result = platform_annotation_to_ls(payload.label)
        await ls_client.create_annotation(sample_row.ls_task_id, ls_result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Label Studio annotation sync failed: {exc}"
        )
    ann = Annotation(
        sample_id=payload.sample_id,
        label=payload.label,
        annotation_value=payload.annotation_value,
        created_by=current_user.id,
    )
    await storage.create_annotations([ann])
    await event_publisher.publish_annotation_created(
        annotation_id=ann.id,
        sample_id=payload.sample_id,
        dataset_id=payload.dataset_id,
    )
    # ── Auto-expand label_space with newly introduced labels ──────────
    await dataset_service.merge_label_space(
        payload.dataset_id,
        org.id,
        {payload.label},
    )
    return ann


@router.get(
    "/datasets/{dataset_id}/samples/{sample_id}/annotations",
    response_model=list[Annotation],
)
async def list_annotations_for_sample(
    dataset_id: str,
    sample_id: str,
    factory: DatasetStorageFactoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[Annotation]:
    storage = await _open_storage(factory, dataset_id, org_id=org.id)
    return await storage.list_annotations(sample_id=sample_id)


@router.patch("/annotations/{annotation_id}", response_model=Annotation)
async def update_annotation(
    annotation_id: str,
    payload: UpdateAnnotationRequest,
    dataset_service: DatasetServiceDep,
    factory: DatasetStorageFactoryDep,
    event_publisher: RedisEventPublisherDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Annotation:
    storage = await _open_storage(factory, payload.dataset_id, org_id=org.id)
    updated = await storage.update_annotations([(annotation_id, payload.label)])
    if not updated:
        raise HTTPException(status_code=404, detail="annotation not found")
    await event_publisher.publish_annotation_updated(
        annotation_id=annotation_id,
        sample_id="",
        dataset_id=payload.dataset_id,
    )
    # Auto-expand label space if the label is new
    await dataset_service.merge_label_space(
        payload.dataset_id,
        org.id,
        {payload.label},
    )
    return Annotation(
        id=annotation_id,
        sample_id="",
        label=payload.label,
        created_by=current_user.id,
    )


@router.delete("/annotations/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: str,
    factory: DatasetStorageFactoryDep,
    event_publisher: RedisEventPublisherDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    dataset_id: str = Query(description="Dataset ID for storage-mode dispatch"),
) -> Response:
    storage = await _open_storage(factory, dataset_id, org_id=org.id)
    deleted = await storage.delete_annotations([annotation_id])
    if not deleted:
        raise HTTPException(status_code=404, detail="annotation not found")
    await event_publisher.publish_annotation_deleted(
        annotation_id=annotation_id,
        sample_id="",
        dataset_id=dataset_id,
    )
    return Response(status_code=204)


@router.post(
    "/datasets/{dataset_id}/annotations/bulk",
    response_model=BulkAnnotationResponse,
)
async def bulk_create_annotations(
    dataset_id: str,
    payload: BulkAnnotationRequest,
    dataset_service: DatasetServiceDep,
    factory: DatasetStorageFactoryDep,
    event_publisher: RedisEventPublisherDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> BulkAnnotationResponse:
    storage = await _open_storage(factory, dataset_id, org_id=org.id)
    ann_list = [
        Annotation(
            id=uuid4().hex,
            sample_id=item.sample_id,
            label=item.label,
            created_by=current_user.id,
        )
        for item in payload.annotations
    ]
    created = await storage.create_annotations(ann_list)

    for ann in ann_list:
        await event_publisher.publish_annotation_created(
            annotation_id=ann.id,
            sample_id=ann.sample_id,
            dataset_id=dataset_id,
        )

    # ── Auto-expand label_space with newly introduced labels ──────────
    incoming_labels = {a.label for a in payload.annotations}
    await dataset_service.merge_label_space(dataset_id, org.id, incoming_labels)

    return BulkAnnotationResponse(created=created)


@router.post(
    "/datasets/{dataset_id}/sync-annotations-to-ls",
    response_model=SyncAnnotationsResponse,
)
async def sync_annotations_to_ls(
    dataset_id: str,
    ls_client: LabelStudioClientDep,
    factory: DatasetStorageFactoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
) -> SyncAnnotationsResponse:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not dataset.ls_project_id or dataset.ls_project_id == SPARSE_NO_LS:
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot sync annotations.",
        )

    storage = await _open_storage(factory, dataset_id, org_id=org.id)
    synced_count = 0
    errors: list[str] = []
    from app.shared.infrastructure.label_studio.client import platform_annotation_to_ls

    offset = 0
    while True:
        annotated_rows, total = await storage.list_samples(
            offset=offset,
            limit=_ANNOTATION_SYNC_PAGE_SIZE,
            with_labels=True,
        )
        for row in annotated_rows:
            if row.latest_label is None:
                continue
            if not row.ls_task_id:
                errors.append(
                    f"annotation for sample {row.sample_id}: "
                    "sample has no ls_task_id — cannot sync"
                )
                continue
            try:
                ls_result = platform_annotation_to_ls(row.latest_label)
                await ls_client.create_annotation(row.ls_task_id, ls_result)
                synced_count += 1
            except Exception as exc:
                errors.append(f"annotation for sample {row.sample_id}: {str(exc)}")

        offset += len(annotated_rows)
        if offset >= total:
            break
        if not annotated_rows:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Dataset storage returned an empty page before the reported total"
                ),
            )

    return SyncAnnotationsResponse(synced_count=synced_count, errors=errors)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.get("/exports/{dataset_id}")
async def export_dataset(
    dataset_id: str,
    service: DatasetServiceDep,
    session_factory: SessionFactoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
    ls_read_repository_factory: LsReadRepositoryFactory = Depends(
        get_ls_read_repository_factory
    ),
    artifacts: ArtifactService = Depends(get_artifact_service),
    payload_store: DatasetPayloadStore = Depends(get_dataset_payload_store),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> dict:
    dataset_check = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset_check is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset_check.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
        assembler = SparseExportAssembler(
            store=payload_store,
            reader=SparseManifestReader(),
            storage=storage,
            session_factory=session_factory.sessionmaker,
        )
        return await assembler.assemble(dataset_check, org.id)
    if not dataset_check.ls_project_id:
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot export.",
        )
    ls_read_repository = _open_ls_read_repository(ls_read_repository_factory)
    dataset, samples, anns = await service.build_export_data(
        dataset_id, org.id, ls_read_repository
    )
    return artifacts.build_dataset_export(
        dataset=dataset,
        samples=samples,
        annotations=anns,
    )


@router.post("/exports/{dataset_id}/persist", response_model=PersistExportResponse)
async def export_dataset_persist(
    dataset_id: str,
    service: DatasetServiceDep,
    session_factory: SessionFactoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
    ls_read_repository_factory: LsReadRepositoryFactory = Depends(
        get_ls_read_repository_factory
    ),
    artifacts: ArtifactService = Depends(get_artifact_service),
    payload_store: DatasetPayloadStore = Depends(get_dataset_payload_store),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> PersistExportResponse:
    dataset_check = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset_check is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset_check.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
        assembler = SparseExportAssembler(
            store=payload_store,
            reader=SparseManifestReader(),
            storage=storage,
            session_factory=session_factory.sessionmaker,
        )
        uri = await assembler.assemble_and_persist(dataset_check, org.id)
        return PersistExportResponse(uri=uri)
    if not dataset_check.ls_project_id:
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot export.",
        )
    ls_read_repository = _open_ls_read_repository(ls_read_repository_factory)
    dataset, samples, anns = await service.build_export_data(
        dataset_id, org.id, ls_read_repository
    )
    uri = await artifacts.persist_dataset_export(
        dataset=dataset, samples=samples, annotations=anns
    )
    return PersistExportResponse(uri=uri)


@router.post("/exports/{dataset_id}/persist/stream")
async def export_dataset_persist_stream(
    dataset_id: str,
    request: Request,
    service: DatasetServiceDep,
    session_factory: SessionFactoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: DatasetRepository = Depends(get_repository),
    ls_read_repository_factory: LsReadRepositoryFactory = Depends(
        get_ls_read_repository_factory
    ),
    artifacts: ArtifactService = Depends(get_artifact_service),
    payload_store: DatasetPayloadStore = Depends(get_dataset_payload_store),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> StreamingResponse:
    async def event_generator():
        if await request.is_disconnected():
            return
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="dataset.export.persist",
                    status="loading",
                    message="Preparing dataset export",
                )
            )
        )
        try:
            result = await export_dataset_persist(
                dataset_id,
                service,
                session_factory,
                current_user,
                org,
                repo,
                ls_read_repository_factory,
                artifacts,
                payload_store,
                storage,
            )
        except Exception as exc:
            yield emit_sse(
                SSEEvent(
                    ScErrorEvent(
                        event_type="error",
                        status="failed",
                        error=str(exc),
                    )
                )
            )
            return
        yield emit_sse(
            SSEEvent(
                ScDataEvent(
                    event_type="data",
                    operation="dataset.export.persist",
                    payload=result.model_dump(mode="json"),
                )
            )
        )
        yield emit_sse(SSEEvent(DoneEvent(event_type="done", uri=result.uri)))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/download")
async def download_export(
    uri: str = Query(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> Response:
    try:
        data = await storage.get_bytes(uri)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="export artifact not found")
    filename = uri.rsplit("/", 1)[-1] if "/" in uri else uri
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Features & Similarity
# ---------------------------------------------------------------------------


@router.get(
    "/datasets/{dataset_id}/similarity/{sample_id}", response_model=SimilarityResponse
)
async def similarity_search(
    dataset_id: str,
    sample_id: str,
    factory: DatasetStorageFactoryDep,
    sample_similarity: SampleSimilarityDep,
    k: int = 5,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    storage = await _open_storage(factory, dataset_id, org_id=org.id)
    sample_row = await storage.get_sample(sample_id)
    if sample_row is None:
        raise HTTPException(status_code=404, detail="sample not found")
    return await sample_similarity.similarity_search(
        sample_id,
        dataset_id=dataset_id,
        org_id=org.id,
        k=k,
    )


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    repo: ArtifactLookupRepositoryDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> Response:
    artifact = await repo.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        data = await storage.get_bytes(artifact.uri)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="artifact data not found")
    return Response(content=data, media_type="application/octet-stream")
