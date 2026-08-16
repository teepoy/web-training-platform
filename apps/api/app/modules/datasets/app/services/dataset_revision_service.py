from __future__ import annotations

import logging
from uuid import uuid4

from injector import inject

from app.modules.datasets.domain.entities import (
    DatasetRevision,
    DatasetRevisionOperation,
)
from app.modules.datasets.domain.repository import (
    DatasetRepository,
    DatasetRevisionRepository,
)
from app.modules.storage.domain.sparse import DatasetPayloadStore
from app.shared.api.schemas import Dataset, DatasetStorageMode

_logger = logging.getLogger(__name__)


class DatasetNotFoundError(LookupError):
    pass


class DatasetRevisionNotFoundError(LookupError):
    pass


class DatasetRevisionConflictError(RuntimeError):
    pass


class DatasetRevisionService:
    @inject
    def __init__(
        self,
        repository: DatasetRepository,
        revision_repository: DatasetRevisionRepository,
        payload_store: DatasetPayloadStore,
    ) -> None:
        self._repository = repository
        self._revision_repository = revision_repository
        self._payload_store = payload_store

    async def publish_sparse_revision(
        self,
        *,
        dataset_id: str,
        org_id: str,
        operation: DatasetRevisionOperation,
        created_by: str,
        provenance: dict[str, object] | None = None,
        operation_ref: str | None = None,
    ) -> DatasetRevision:
        dataset = await self._require_dataset(dataset_id, org_id)
        if dataset.org_id != org_id:
            raise DatasetNotFoundError(dataset_id)
        if dataset.storage_mode != DatasetStorageMode.FILE_SHARD_SPARSE:
            raise ValueError(
                "Dataset Revision publication is not implemented for db_full storage"
            )

        current = await self._revision_repository.get_current_revision(
            dataset_id,
            org_id,
        )
        if operation == DatasetRevisionOperation.INITIAL_IMPORT and current is not None:
            raise DatasetRevisionConflictError(
                "Initial import Revision has already been published"
            )
        if (
            operation
            not in {
                DatasetRevisionOperation.INITIAL_IMPORT,
                DatasetRevisionOperation.LEGACY_BASELINE,
            }
            and current is None
        ):
            raise DatasetRevisionConflictError(
                "A legacy baseline Revision must be published before this operation"
            )

        revision_id = str(uuid4())
        manifest_uri = await self._write_audit_manifest(
            dataset=dataset,
            org_id=org_id,
            revision_id=revision_id,
        )
        try:
            revision = await self._revision_repository.publish_revision(
                revision_id=revision_id,
                dataset_id=dataset_id,
                org_id=org_id,
                manifest_uri=manifest_uri,
                provenance=provenance or {},
                operation=operation,
                operation_ref=operation_ref,
                created_by=created_by,
            )
            if revision.id != revision_id:
                await self._delete_orphan_manifest(manifest_uri)
            return revision
        except BaseException:
            try:
                await self._payload_store.storage.delete(manifest_uri)
            except Exception:
                _logger.warning(
                    "Failed to clean archived manifest %s after Revision persistence error",
                    manifest_uri,
                    exc_info=True,
                )
            raise

    async def resolve_or_create_baseline(
        self,
        *,
        dataset_id: str,
        org_id: str,
        created_by: str,
    ) -> DatasetRevision:
        """Resolve current audit Revision or lazily create a legacy baseline.

        Historical datasets intentionally have no migration-time backfill. The
        first revision-aware consumer records source metadata and a canonical
        current-data reference. It does not copy rows, images, or annotations,
        and therefore is explicitly not reproducible.
        """
        current = await self._revision_repository.get_current_revision(
            dataset_id,
            org_id,
        )
        if current is not None:
            return current

        dataset = await self._require_dataset(dataset_id, org_id)
        owner_org_id = dataset.org_id or org_id
        revision_id = str(uuid4())
        manifest_uri = await self._write_audit_manifest(
            dataset=dataset,
            org_id=owner_org_id,
            revision_id=revision_id,
        )
        try:
            revision = await self._revision_repository.publish_revision(
                revision_id=revision_id,
                dataset_id=dataset_id,
                org_id=owner_org_id,
                manifest_uri=manifest_uri,
                provenance={"reason": "first_revision_aware_consumer"},
                operation=DatasetRevisionOperation.LEGACY_BASELINE,
                operation_ref=None,
                created_by=created_by,
            )
            if revision.id != revision_id:
                await self._delete_orphan_manifest(manifest_uri)
            return revision
        except BaseException:
            await self._delete_orphan_manifest(manifest_uri)
            raise

    async def _delete_orphan_manifest(self, manifest_uri: str) -> None:
        try:
            await self._payload_store.storage.delete(manifest_uri)
        except Exception:
            _logger.warning(
                "Failed to clean orphaned Dataset Revision manifest %s",
                manifest_uri,
                exc_info=True,
            )

    async def get_revision(
        self,
        *,
        dataset_id: str,
        revision_id: str,
        org_id: str,
    ) -> DatasetRevision:
        revision = await self._revision_repository.get_revision(
            dataset_id,
            revision_id,
            org_id,
        )
        if revision is not None:
            return revision
        await self._require_dataset(dataset_id, org_id)
        raise DatasetRevisionNotFoundError(revision_id)

    async def _write_audit_manifest(
        self,
        *,
        dataset: Dataset,
        org_id: str,
        revision_id: str,
    ) -> str:
        source_reference: dict[str, object]
        if dataset.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
            source_reference = {
                "kind": "canonical_manifest",
                "object_key": self._payload_store.get_manifest_key(
                    dataset.id,
                    org_id,
                ),
            }
        else:
            source_reference = {
                "kind": "database_current",
                "dataset_id": dataset.id,
            }
        return await self._payload_store.put_revision_manifest_document(
            dataset_id=dataset.id,
            org_id=org_id,
            revision_id=revision_id,
            document={
                "manifest_schema_version": "dataset-revision-audit-manifest.v1",
                "dataset_id": dataset.id,
                "dataset_type": dataset.dataset_type,
                "storage_mode": dataset.storage_mode.value,
                "view_types": dataset.view_types,
                "task_spec": dataset.task_spec.model_dump(mode="json"),
                "source_reference": source_reference,
                "is_reproducible": False,
            },
        )

    async def get_current(self, dataset_id: str, org_id: str) -> DatasetRevision:
        revision = await self._revision_repository.get_current_revision(
            dataset_id,
            org_id,
        )
        if revision is not None:
            return revision
        await self._require_dataset(dataset_id, org_id)
        raise DatasetRevisionNotFoundError(dataset_id)

    async def list_current(
        self, dataset_ids: tuple[str, ...], org_id: str
    ) -> dict[str, DatasetRevision]:
        return await self._revision_repository.list_current_revisions(
            dataset_ids,
            org_id,
        )

    async def list_history(
        self,
        dataset_id: str,
        org_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[DatasetRevision], int]:
        await self._require_dataset(dataset_id, org_id)
        revisions = await self._revision_repository.list_revisions(
            dataset_id,
            org_id,
            limit=limit,
            offset=offset,
        )
        total = await self._revision_repository.count_revisions(dataset_id, org_id)
        return revisions, total

    async def _require_dataset(self, dataset_id: str, org_id: str) -> Dataset:
        dataset = await self._repository.get_dataset(dataset_id, org_id=org_id)
        if dataset is None:
            raise DatasetNotFoundError(dataset_id)
        return dataset
