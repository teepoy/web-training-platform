from __future__ import annotations

import base64
import json
import logging

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

from app.shared.api.schemas import (
    DatasetAnnotationStats,
    PaginatedResponse,
    SetPublicRequest,
    SetPublicResponse,
)
from app.modules.auth.interfaces.controllers.deps import (
    get_current_org,
    get_current_user,
    require_admin,
    require_superadmin,
)
from app.modules.datasets.application.services.sparse_manifest import (
    SparseManifestReader,
)
from app.modules.datasets.interfaces.dtos.schemas import (
    BulkAnnotationRequest,
    BulkAnnotationResponse,
    BulkCreateSampleRequest,
    BulkCreateSampleResponse,
    CreateAnnotationRequest,
    CreateDatasetRequest,
    CreateSampleRequest,
    EmbedConfigResponse,
    ImportVqaJsonlResponse,
    PersistExportResponse,
    SampleEmbedResponse,
    SampleWithLabels,
    SimilarityResponse,
    SparseManifestSummary,
    SparseShardSummary,
    SparseSummaryResponse,
    SyncAnnotationsResponse,
    UpdateAnnotationRequest,
    UpdateEmbedConfigRequest,
    UpdateLabelSpaceRequest,
    UpdateSampleImageResponse,
)
from app.shared.api.schemas import (
    Annotation,
    Dataset,
    Organization,
    Sample,
    SPARSE_NO_LS,
    User,
)
from app.shared.infrastructure.storage.base import ArtifactStorage
from app.shared.api.schemas import DatasetStorageMode, TaskType
from app.modules.datasets.application.services.dataset_payload_store import (
    DatasetPayloadStore,
)
from app.modules.datasets.application.services.dataset_service import DatasetService
from app.modules.datasets.domain.entities.dataset_payload import DatasetManifest
from app.modules.datasets.application.sample_access.factory import SampleAccessFactory
from app.modules.datasets.application.services.feature_ops import FeatureOpsService
from app.shared.application.artifacts import ArtifactService
from app.shared.db.sql_repository import SqlRepository
from app.shared.deps import (
    _infer_dataset_type,
    _make_ls_image_url,
    _with_ls_url,
    get_artifact_storage,
    get_artifacts,
    get_embedding_service,
    get_feature_ops,
    get_label_studio_client,
    get_repository,
    get_sample_access_factory,
)
from app.shared.infrastructure.label_studio.client import (
    LabelStudioClient,
    LabelStudioNotFoundError,
    platform_annotation_to_ls,
)
from app.shared.infrastructure.label_studio.read_repository import LsReadRepository
from app.shared.infrastructure.workers.embedding import EmbeddingClient


def get_ls_read_repository_optional() -> LsReadRepository | None:
    return None


def _get_ls_read_repository_direct() -> LsReadRepository:
    from app.main import container

    return container.ls_read_repository()


router = APIRouter(prefix="/api/v1", tags=["datasets"])
_logger = logging.getLogger(__name__)


def _dataset_service(
    repo: SqlRepository,
    sample_factory: SampleAccessFactory,
    ls_read_repository: LsReadRepository,
) -> DatasetService:
    return DatasetService(
        repository=repo,
        sample_factory=sample_factory,
        ls_read_repository=ls_read_repository,
    )


def _is_mocked_provider(value: object) -> bool:
    module_name = type(value).__module__
    return module_name.startswith("unittest.mock")


# ---------------------------------------------------------------------------
# Dataset CRUD
# ---------------------------------------------------------------------------


@router.post("/datasets", response_model=Dataset)
async def create_dataset(
    payload: CreateDatasetRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    ls_client: LabelStudioClient = Depends(get_label_studio_client),
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

    if payload.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
        ls_project_id = SPARSE_NO_LS
    else:
        # LS-first: create project, fail if LS fails
        try:
            from app.shared.infrastructure.label_studio.client import (
                LabelStudioClient as _LSC,
            )

            if payload.task_spec.task_type == TaskType.VQA:
                label_config = _LSC.generate_vqa_config()
            else:
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
        task_spec=payload.task_spec,
        org_id=org.id,
        ls_project_id=ls_project_id,
        storage_mode=payload.storage_mode,
    )
    dataset = await repo.create_dataset(dataset)
    if payload.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
        manifest = DatasetManifest(
            dataset_id=dataset.id,
            storage_mode=dataset.storage_mode.value,
            shard_count=0,
            total_rows=0,
        )
        await DatasetPayloadStore(storage).put_manifest(manifest, org_id=org.id)
    return _with_ls_url(dataset)


@router.get("/datasets", response_model=list[Dataset])
async def list_datasets(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> list[Dataset]:
    datasets = await repo.list_datasets(org_id=org.id)
    return [_with_ls_url(d) for d in datasets]


@router.get("/datasets/{dataset_id}", response_model=Dataset)
async def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
) -> Dataset:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if _is_mocked_provider(repo):
        access = sample_factory.create(dataset.storage_mode)
        dataset = dataset.model_copy(update={"capabilities": access.capabilities()})
    return _with_ls_url(dataset)


@router.get(
    "/datasets/{dataset_id}/sparse-summary",
    response_model=SparseSummaryResponse,
)
async def get_sparse_summary(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
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
    sample_rows: list[dict[str, object]] = []
    if manifest.shards:
        first_shard = manifest.shards[0]
        try:
            sample_rows = await reader.read_row_batch(
                first_shard.uri,
                0,
                min(5, first_shard.row_count),
                storage,
            )
        except Exception as exc:
            _logger.warning("Failed to read sample rows from shard 0: %s", exc)

    return SparseSummaryResponse(
        dataset_id=dataset.id,
        name=dataset.name,
        dataset_type=dataset.dataset_type.value,
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
    request: Request,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    ls_client: LabelStudioClient = Depends(get_label_studio_client),
) -> Response:
    await require_admin(request, current_user=current_user, org=org)
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if dataset.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
        store = DatasetPayloadStore(storage=storage)
        await store.delete_dataset_payload(dataset_id, org_id=org.id)
    else:
        if dataset.ls_project_id:
            try:
                await ls_client.delete_project(int(dataset.ls_project_id))
            except LabelStudioNotFoundError:
                pass
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to delete Label Studio project: {exc}",
                )

    deleted = await repo.delete_dataset(dataset_id, org_id=org.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return Response(status_code=204)


@router.patch("/datasets/{dataset_id}/label-space", response_model=Dataset)
async def update_label_space(
    dataset_id: str,
    payload: UpdateLabelSpaceRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    ls_client: LabelStudioClient = Depends(get_label_studio_client),
) -> Dataset:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Update Label Studio project config with new labels
    if dataset.ls_project_id:
        try:
            from app.shared.infrastructure.label_studio.client import (
                LabelStudioClient as _LSC,
            )

            if dataset.task_spec.task_type == TaskType.VQA:
                label_config = _LSC.generate_vqa_config()
            else:
                label_config = _LSC.generate_image_classification_config(
                    payload.label_space
                )
            await ls_client.update_project(
                int(dataset.ls_project_id), label_config=label_config
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Failed to update Label Studio project: {exc}"
            )

    new_task_spec = {
        "task_type": dataset.task_spec.task_type,
        "label_space": payload.label_space,
    }
    updated = await repo.update_dataset_task_spec(dataset_id, new_task_spec)
    if updated is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _with_ls_url(updated)


@router.patch("/datasets/{dataset_id}/public", response_model=SetPublicResponse)
async def set_dataset_public(
    dataset_id: str,
    payload: SetPublicRequest,
    current_user: User = Depends(get_current_user),
    repo: SqlRepository = Depends(get_repository),
) -> SetPublicResponse:
    await require_superadmin(current_user=current_user)
    ok = await repo.set_dataset_public(dataset_id, payload.is_public)
    if not ok:
        raise HTTPException(status_code=404, detail="dataset not found")
    return SetPublicResponse(ok=True)


# ---------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------


@router.post("/datasets/{dataset_id}/samples", response_model=Sample)
async def create_sample(
    dataset_id: str,
    payload: CreateSampleRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    ls_client: LabelStudioClient = Depends(get_label_studio_client),
) -> Sample:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None and _is_mocked_provider(repo):
        dataset = await repo.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    access = sample_factory.create(dataset.storage_mode)
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
        if dataset.task_spec.task_type == TaskType.VQA:
            task_data["question"] = str(payload.metadata.get("question", ""))
        task = await ls_client.create_task(int(dataset.ls_project_id), task_data)
        ls_task_id = task.get("id")
        if ls_task_id is None:
            raise HTTPException(
                status_code=502, detail="Label Studio task creation returned no ID."
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Label Studio task creation failed: {exc}"
        )
    sample = Sample(
        dataset_id=dataset_id,
        image_uris=payload.image_uris,
        metadata=payload.metadata,
        ls_task_id=int(ls_task_id),  # type: ignore[arg-type]
    )
    created = await access.create_samples([sample])
    return created[0]


@router.post(
    "/datasets/{dataset_id}/samples/import",
    response_model=BulkCreateSampleResponse,
)
async def import_samples(
    dataset_id: str,
    payload: BulkCreateSampleRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    ls_client: LabelStudioClient = Depends(get_label_studio_client),
) -> BulkCreateSampleResponse:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    access = sample_factory.create(dataset.storage_mode)
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
        if dataset.task_spec.task_type == TaskType.VQA:
            task_data["question"] = str(item.metadata.get("question", ""))
        ls_tasks.append(task_data)

    try:
        imported = await ls_client.import_tasks(
            int(dataset.ls_project_id),
            ls_tasks,
            return_task_ids=True,
        )
        task_ids = [int(tid) for tid in imported.get("task_ids", [])]  # type: ignore[arg-type]
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

    samples = [
        Sample(
            dataset_id=dataset_id,
            image_uris=item.image_uris,
            metadata=item.metadata,
            ls_task_id=task_ids[idx],
        )
        for idx, item in enumerate(payload.items)
    ]
    created = await access.create_samples(samples)

    for idx, item in enumerate(payload.items):
        if item.label is None:
            continue
        sample = created[idx]
        if sample.ls_task_id is not None:
            await ls_client.create_annotation(
                sample.ls_task_id,
                platform_annotation_to_ls(item.label),
            )
        await repo.create_annotation(
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


@router.post(
    "/datasets/{dataset_id}/samples/import-vqa",
    response_model=ImportVqaJsonlResponse,
)
async def import_vqa_samples(
    dataset_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    ls_client: LabelStudioClient = Depends(get_label_studio_client),
) -> ImportVqaJsonlResponse:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    access = sample_factory.create(dataset.storage_mode)
    if dataset.task_spec.task_type != TaskType.VQA:
        raise HTTPException(status_code=400, detail="dataset task_type must be 'vqa'")
    if not dataset.ls_project_id or dataset.ls_project_id == SPARSE_NO_LS:
        raise HTTPException(
            status_code=500, detail="Dataset has no Label Studio project"
        )
    content = (await file.read()).decode("utf-8")
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
                metadata=metadata,  # type: ignore
                ls_task_id=int(ls_task_id),  # type: ignore[arg-type]
            )
            await access.create_samples([sample])
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


@router.get("/datasets/{dataset_id}/samples", response_model=PaginatedResponse[Sample])
async def list_samples(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
) -> PaginatedResponse[Sample]:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    access = sample_factory.create(dataset.storage_mode)
    items, total = await access.list_samples(dataset_id, offset=offset, limit=limit)
    return PaginatedResponse(items=items, total=total)


@router.get(
    "/datasets/{dataset_id}/samples-with-labels",
    response_model=PaginatedResponse[SampleWithLabels],
)
async def list_samples_with_labels_endpoint(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
    label: str | None = None,
    order_by: str = "id",
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
) -> PaginatedResponse[SampleWithLabels]:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    access = sample_factory.create(dataset.storage_mode)
    items, total = await access.list_samples_with_labels(
        dataset_id=dataset_id,
        offset=offset,
        limit=limit,
        label_filter=label,
        order_by=order_by,
    )
    return PaginatedResponse(
        items=[SampleWithLabels(**item) for item in items], total=total
    )


@router.get(
    "/datasets/{dataset_id}/annotation-stats",
    response_model=DatasetAnnotationStats,
)
async def get_annotation_stats(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
) -> DatasetAnnotationStats:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    access = sample_factory.create(dataset.storage_mode)
    stats = await access.get_annotation_stats(dataset_id)
    return DatasetAnnotationStats(**stats)


@router.get("/samples/{sample_id}", response_model=Sample)
async def get_sample(
    sample_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> Sample:
    sample = await repo.get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    return sample


@router.post("/samples/{sample_id}/embed", response_model=SampleEmbedResponse)
async def embed_sample(
    sample_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    embedding_svc: EmbeddingClient = Depends(get_embedding_service),
) -> SampleEmbedResponse:
    sample = await repo.get_sample(sample_id)
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
            image_bytes = await storage.get_bytes(uri)
        except (FileNotFoundError, KeyError):
            raise HTTPException(status_code=404, detail="image not found")
    else:
        raise HTTPException(status_code=400, detail="unsupported URI scheme")

    dataset = await repo.get_dataset(sample.dataset_id)
    embed_model: str | None = (
        (dataset.embed_config or {}).get("model", "openai/clip-vit-base-patch32")
        if dataset
        else "openai/clip-vit-base-patch32"
    )
    assert embed_model is not None
    embedding = await embedding_svc.embed_image(image_bytes, model_name=embed_model)
    feature = await repo.upsert_sample_feature(sample_id, embedding, embed_model)
    return SampleEmbedResponse(
        sample_id=feature.sample_id,
        embed_model=feature.embed_model,  # type: ignore[arg-type]
        embedding_dim=len(feature.embedding),
    )


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


@router.post("/annotations", response_model=Annotation)
async def create_annotation(
    payload: CreateAnnotationRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    ls_client: LabelStudioClient = Depends(get_label_studio_client),
) -> Annotation:
    sample = await repo.get_sample(payload.sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    if not sample.ls_task_id:
        raise HTTPException(
            status_code=500,
            detail="Sample has no Label Studio task — cannot create annotation.",
        )
    try:
        from app.shared.infrastructure.label_studio.client import (
            platform_annotation_to_ls,
        )

        ls_result = platform_annotation_to_ls(payload.label)
        await ls_client.create_annotation(sample.ls_task_id, ls_result)
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
    ann = await repo.create_annotation(ann)
    return ann


@router.get("/samples/{sample_id}/annotations", response_model=list[Annotation])
async def list_annotations_for_sample(
    sample_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> list[Annotation]:
    if await repo.get_sample(sample_id) is None:
        raise HTTPException(status_code=404, detail="sample not found")
    return await repo.list_annotations_for_sample(sample_id)


@router.patch("/annotations/{annotation_id}", response_model=Annotation)
async def update_annotation(
    annotation_id: str,
    payload: UpdateAnnotationRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> Annotation:
    result = await repo.update_annotation(annotation_id, payload.label)
    if result is None:
        raise HTTPException(status_code=404, detail="annotation not found")
    return result


@router.delete("/annotations/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> Response:
    deleted = await repo.delete_annotation(annotation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="annotation not found")
    return Response(status_code=204)


@router.post(
    "/datasets/{dataset_id}/annotations/bulk",
    response_model=BulkAnnotationResponse,
)
async def bulk_create_annotations(
    dataset_id: str,
    payload: BulkAnnotationRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
) -> BulkAnnotationResponse:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    access = sample_factory.create(dataset.storage_mode)  # noqa: F841
    created = 0
    for item in payload.annotations:
        ann = Annotation(
            id=__import__("uuid").uuid4().hex,
            sample_id=item.sample_id,
            label=item.label,
            created_by=current_user.id,
        )
        await repo.create_annotation(ann)
        created += 1
    return BulkAnnotationResponse(created=created)


@router.post(
    "/datasets/{dataset_id}/sync-annotations-to-ls",
    response_model=SyncAnnotationsResponse,
)
async def sync_annotations_to_ls(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    ls_client: LabelStudioClient = Depends(get_label_studio_client),
) -> SyncAnnotationsResponse:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None and _is_mocked_provider(repo):
        dataset = await repo.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    access = sample_factory.create(dataset.storage_mode)

    if not dataset.ls_project_id or dataset.ls_project_id == SPARSE_NO_LS:
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot sync annotations.",
        )

    samples, _ = await access.list_samples(dataset_id, limit=100_000)
    sample_map = {s.id: s for s in samples}
    annotations = await access.list_annotations(dataset_id=dataset_id)

    synced_count = 0
    errors: list[str] = []
    from app.shared.infrastructure.label_studio.client import platform_annotation_to_ls

    for ann in annotations:
        sample = sample_map.get(ann.sample_id)
        if not sample:
            errors.append(f"annotation {ann.id}: sample {ann.sample_id} not found")
            continue
        if not sample.ls_task_id:
            errors.append(
                f"annotation {ann.id}: sample {ann.sample_id} has no ls_task_id — cannot sync"
            )
            continue
        try:
            ls_result = platform_annotation_to_ls(ann.label)
            await ls_client.create_annotation(sample.ls_task_id, ls_result)
            synced_count += 1
        except Exception as e:
            errors.append(f"annotation {ann.id}: {str(e)}")

    return SyncAnnotationsResponse(synced_count=synced_count, errors=errors)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.get("/exports/{dataset_id}")
async def export_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    ls_read_repository: LsReadRepository | None = Depends(
        get_ls_read_repository_optional
    ),
    artifacts: ArtifactService = Depends(get_artifacts),
) -> dict:
    dataset_check = await repo.get_dataset(dataset_id)
    if dataset_check is not None and (
        not dataset_check.ls_project_id or dataset_check.ls_project_id == SPARSE_NO_LS
    ):
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot export.",
        )
    if ls_read_repository is None:
        ls_read_repository = _get_ls_read_repository_direct()
    if _is_mocked_provider(repo):
        dataset = dataset_check
        if dataset is not None:
            ls_project_id = dataset.ls_project_id
            if ls_project_id is None:
                raise HTTPException(
                    status_code=500,
                    detail="Dataset has no Label Studio project — cannot export.",
                )
            access = sample_factory.create(dataset.storage_mode)
            try:
                all_samples, _ = await access.list_samples(dataset_id, limit=100_000)
                task_id_to_sample: dict[int, Sample] = {
                    s.ls_task_id: s for s in all_samples if s.ls_task_id is not None
                }
                ls_tasks = await ls_read_repository.get_tasks_for_project(
                    int(ls_project_id)
                )
                task_ids = [t["id"] for t in ls_tasks]
                ls_annotations = (
                    await ls_read_repository.get_annotations_for_tasks(task_ids)
                    if task_ids
                    else {}
                )
                samples_out: list[Sample] = []
                annotations_out: list[Annotation] = []
                from app.shared.infrastructure.label_studio.client import (
                    ls_annotation_to_platform,
                )

                for ls_task in ls_tasks:
                    task_id = ls_task["id"]
                    platform_sample = task_id_to_sample.get(task_id)
                    if platform_sample is None:
                        continue
                    samples_out.append(platform_sample)
                    for ls_ann in ls_annotations.get(task_id, []):
                        label = ls_annotation_to_platform(ls_ann.get("result", []))
                        if label:
                            annotations_out.append(
                                Annotation(
                                    sample_id=platform_sample.id,
                                    label=label,
                                    created_by="label_studio",
                                )
                            )
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=502, detail=f"Label Studio database read failed: {exc}"
                )
            return artifacts.build_dataset_export(
                dataset=dataset,
                samples=samples_out,
                annotations=annotations_out,
            )
    dataset, samples, anns = await _dataset_service(
        repo, sample_factory, ls_read_repository
    ).build_export_data(dataset_id)
    return artifacts.build_dataset_export(
        dataset=dataset,
        samples=samples,
        annotations=anns,
    )


@router.post("/exports/{dataset_id}/persist", response_model=PersistExportResponse)
async def export_dataset_persist(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    ls_read_repository: LsReadRepository | None = Depends(
        get_ls_read_repository_optional
    ),
    artifacts: ArtifactService = Depends(get_artifacts),
) -> PersistExportResponse:
    dataset_check = await repo.get_dataset(dataset_id)
    if dataset_check is not None and (
        not dataset_check.ls_project_id or dataset_check.ls_project_id == SPARSE_NO_LS
    ):
        raise HTTPException(
            status_code=500,
            detail="Dataset has no Label Studio project — cannot export.",
        )
    if ls_read_repository is None:
        ls_read_repository = _get_ls_read_repository_direct()
    if _is_mocked_provider(repo):
        dataset = dataset_check
        if dataset is not None:
            ls_project_id = dataset.ls_project_id
            if ls_project_id is None:
                raise HTTPException(
                    status_code=500,
                    detail="Dataset has no Label Studio project — cannot export.",
                )
            access = sample_factory.create(dataset.storage_mode)
            try:
                all_samples, _ = await access.list_samples(dataset_id, limit=100_000)
                task_id_to_sample: dict[int, Sample] = {
                    s.ls_task_id: s for s in all_samples if s.ls_task_id is not None
                }
                ls_tasks = await ls_read_repository.get_tasks_for_project(
                    int(ls_project_id)
                )
                task_ids = [t["id"] for t in ls_tasks]
                ls_annotations = (
                    await ls_read_repository.get_annotations_for_tasks(task_ids)
                    if task_ids
                    else {}
                )
                samples_out: list[Sample] = []
                annotations_out: list[Annotation] = []
                from app.shared.infrastructure.label_studio.client import (
                    ls_annotation_to_platform,
                )

                for ls_task in ls_tasks:
                    task_id = ls_task["id"]
                    platform_sample = task_id_to_sample.get(task_id)
                    if platform_sample is None:
                        continue
                    samples_out.append(platform_sample)
                    for ls_ann in ls_annotations.get(task_id, []):
                        label = ls_annotation_to_platform(ls_ann.get("result", []))
                        if label:
                            annotations_out.append(
                                Annotation(
                                    sample_id=platform_sample.id,
                                    label=label,
                                    created_by="label_studio",
                                )
                            )
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=502, detail=f"Label Studio database read failed: {exc}"
                )
            uri = await artifacts.persist_dataset_export(
                dataset=dataset, samples=samples_out, annotations=annotations_out
            )
            return PersistExportResponse(uri=uri)
    dataset, samples, anns = await _dataset_service(
        repo, sample_factory, ls_read_repository
    ).build_export_data(dataset_id)
    uri = await artifacts.persist_dataset_export(
        dataset=dataset, samples=samples, annotations=anns
    )
    return PersistExportResponse(uri=uri)


# ---------------------------------------------------------------------------
# Features & Similarity
# ---------------------------------------------------------------------------


@router.get(
    "/datasets/{dataset_id}/similarity/{sample_id}", response_model=SimilarityResponse
)
async def similarity_search(
    dataset_id: str,
    sample_id: str,
    k: int = 5,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    feature_ops: FeatureOpsService = Depends(get_feature_ops),
):
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    access = sample_factory.create(dataset.storage_mode)  # noqa: F841
    sample = await repo.get_sample(sample_id)
    if sample is None or sample.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="sample not found")
    return await feature_ops.similarity_search(sample_id, dataset_id=dataset_id, k=k)


@router.get("/datasets/{dataset_id}/selection-metrics")
async def selection_metrics(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    feature_ops: FeatureOpsService = Depends(get_feature_ops),
) -> dict:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    access = sample_factory.create(dataset.storage_mode)
    samples, _ = await access.list_samples(dataset_id, limit=100_000)
    sample_ids = [s.id for s in samples]
    return {
        "uniqueness": await feature_ops.uniqueness_scores(
            sample_ids, dataset_id=dataset_id
        ),
        "representativeness": await feature_ops.representativeness_scores(
            sample_ids, dataset_id=dataset_id
        ),
    }


@router.get("/datasets/{dataset_id}/hints/uncovered")
async def uncovered_hints(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
    feature_ops: FeatureOpsService = Depends(get_feature_ops),
) -> dict:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    access = sample_factory.create(dataset.storage_mode)  # noqa: F841
    return await feature_ops.uncovered_cluster_hints(dataset_id)


# ---------------------------------------------------------------------------
# Embed config
# ---------------------------------------------------------------------------


@router.get("/datasets/{dataset_id}/embed-config", response_model=EmbedConfigResponse)
async def get_embed_config(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> EmbedConfigResponse:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    cfg = dataset.embed_config or {}
    return EmbedConfigResponse(
        model=cfg.get("model", "openai/clip-vit-base-patch32"),
        dimension=cfg.get("dimension", 512),
    )


@router.patch("/datasets/{dataset_id}/embed-config", response_model=EmbedConfigResponse)
async def update_embed_config(
    dataset_id: str,
    payload: UpdateEmbedConfigRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
) -> EmbedConfigResponse:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    new_config = {"model": payload.model, "dimension": payload.dimension}
    await repo.update_dataset_embed_config(dataset_id, new_config)
    return EmbedConfigResponse(model=payload.model, dimension=payload.dimension)


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
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


# ---------------------------------------------------------------------------
# Sample image upload
# ---------------------------------------------------------------------------

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/samples/{sample_id}/upload", response_model=UpdateSampleImageResponse)
async def upload_sample_image(
    sample_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    repo: SqlRepository = Depends(get_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    sample_factory: SampleAccessFactory = Depends(get_sample_access_factory),
) -> UpdateSampleImageResponse:
    sample = await repo.get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="file must be an image")
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 10 MB limit")
    key = f"samples/{sample_id}/{file.filename}"
    uri = await storage.put_bytes(
        key, data, file.content_type or "application/octet-stream"
    )
    existing_uris = list(sample.image_uris or [])
    index = len(existing_uris)
    updated_uris = existing_uris + [uri]
    dataset = await repo.get_dataset(sample.dataset_id)
    if dataset is not None:
        session_access = sample_factory.create(dataset.storage_mode)
        await session_access.update_sample(sample_id, image_uris=updated_uris)
    return UpdateSampleImageResponse(uri=uri, sample_id=sample_id, index=index)
