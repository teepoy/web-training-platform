from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from injector import inject

from app.modules.dataset_collections.domain.errors import (
    DatasetCollectionNotFoundError,
    DatasetCollectionPermissionError,
    DatasetCollectionValidationError,
)
from app.modules.dataset_collections.domain.models import (
    CollectionSnapshotRefreshResult,
    CollectionSnapshotMemberUpdate,
    CollectionSnapshotUpdateStatus,
    DatasetCollection,
    DatasetCollectionMember,
    DatasetCollectionRevision,
    NewCollectionMember,
)
from app.modules.dataset_collections.domain.repository import (
    CollectionSortField,
    DatasetCollectionRepository,
    SortDirection,
)
from app.modules.datasets.domain.entities import DatasetRevision
from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.datasets.port.local import DatasetRevisionReaderPort
from app.modules.types.catalog import get_view_meta
from app.shared.api.schemas import Dataset
from app.shared.domain.protocols import ArtifactStorage


_logger = logging.getLogger(__name__)

_COMPOSITE_MANIFEST_FORMAT = "collection-composite-observed.v1"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DatasetCollectionService:
    @inject
    def __init__(
        self,
        repository: DatasetCollectionRepository,
        dataset_reader: DatasetReader,
        dataset_revision_reader: DatasetRevisionReaderPort,
        artifact_storage: ArtifactStorage,
    ) -> None:
        self._repository = repository
        self._dataset_reader = dataset_reader
        self._dataset_revision_reader = dataset_revision_reader
        self._artifact_storage = artifact_storage

    async def create_collection(
        self,
        *,
        org_id: str,
        created_by: str,
        name: str,
        description: str,
        target_view_id: str,
        duplicate_policy: str,
        missing_data_policy: str,
    ) -> DatasetCollection:
        if duplicate_policy != "keep_all":
            raise DatasetCollectionValidationError(
                "unsupported_duplicate_policy",
                "MVP collections require duplicate_policy='keep_all'",
            )
        if missing_data_policy != "fail":
            raise DatasetCollectionValidationError(
                "unsupported_missing_data_policy",
                "MVP collections require missing_data_policy='fail'",
            )
        try:
            view = get_view_meta(target_view_id)
        except KeyError as exc:
            raise DatasetCollectionValidationError(
                "unknown_target_view", f"Unknown target view: {target_view_id}"
            ) from exc
        now = _utcnow()
        return await self._repository.create_collection(
            DatasetCollection(
                id=str(uuid4()),
                org_id=org_id,
                name=name,
                description=description,
                target_view_id=view.ref.view_id,
                target_view_contract=view.ref.contract,
                target_schema_version=view.ref.schema_version,
                duplicate_policy=duplicate_policy,
                missing_data_policy=missing_data_policy,
                definition_version=0,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
        )

    async def list_collections(
        self,
        org_id: str,
        *,
        offset: int,
        limit: int,
        creator_id: str | None = None,
        query: str | None = None,
        sort_by: CollectionSortField = "updated_at",
        sort_order: SortDirection = "desc",
    ) -> tuple[list[DatasetCollection], int]:
        return await self._repository.list_collections(
            org_id,
            offset=offset,
            limit=limit,
            creator_id=creator_id,
            query=query,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    async def get_collection(
        self, collection_id: str, org_id: str
    ) -> DatasetCollection:
        collection = await self._repository.get_collection(collection_id, org_id)
        if collection is None:
            raise DatasetCollectionNotFoundError("Dataset collection not found")
        return collection

    async def update_collection(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        name: str | None,
        description: str | None,
    ) -> DatasetCollection:
        collection = await self.get_collection(collection_id, org_id)
        self._require_owner(collection, actor_id)
        updated = await self._repository.update_collection(
            collection_id,
            org_id,
            name=name,
            description=description,
        )
        if updated is None:
            raise DatasetCollectionNotFoundError("Dataset collection not found")
        return updated

    async def delete_collection(
        self, collection_id: str, org_id: str, *, actor_id: str
    ) -> None:
        collection = await self.get_collection(collection_id, org_id)
        self._require_owner(collection, actor_id)
        artifact_uris = await self._repository.delete_collection(collection_id, org_id)
        if artifact_uris is None:
            raise DatasetCollectionNotFoundError("Dataset collection not found")
        cleanup_results = await asyncio.gather(
            *(self._artifact_storage.delete(uri) for uri in artifact_uris),
            return_exceptions=True,
        )
        cleanup_failures = sum(
            isinstance(result, BaseException) for result in cleanup_results
        )
        if cleanup_failures:
            _logger.warning(
                "Failed to delete %d of %d dataset collection revision artifacts",
                cleanup_failures,
                len(artifact_uris),
            )

    async def list_members(
        self, collection_id: str, org_id: str
    ) -> list[DatasetCollectionMember]:
        return await self._repository.list_active_members(collection_id, org_id)

    async def link_members(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        collection = await self.get_collection(collection_id, org_id)
        self._require_owner(collection, actor_id)
        return await self._admit_members(
            collection,
            org_id=org_id,
            actor_id=actor_id,
            expected_definition_version=expected_definition_version,
            members=members,
        )

    async def admit_members_for_automation(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        collection = await self.get_collection(collection_id, org_id)
        return await self._admit_members(
            collection,
            org_id=org_id,
            actor_id=actor_id,
            expected_definition_version=expected_definition_version,
            members=members,
        )

    async def _admit_members(
        self,
        collection: DatasetCollection,
        *,
        org_id: str,
        actor_id: str,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        self._validate_supported_member_specs(members)
        existing = await self._repository.list_active_members(collection.id, org_id)
        existing_ids = {item.source_dataset_id for item in existing}
        requested_ids = {item.source_dataset_id for item in members}
        duplicated = sorted(existing_ids & requested_ids)
        if duplicated:
            raise DatasetCollectionValidationError(
                "dataset_already_linked",
                f"Datasets already linked: {duplicated}",
            )
        await self._validate_members(
            collection,
            (*tuple(item.source_dataset_id for item in existing), *requested_ids),
        )
        self._validate_positions(
            (
                *tuple(item.position for item in existing),
                *(item.position for item in members),
            )
        )
        return await self._repository.link_members(
            collection.id,
            org_id,
            expected_definition_version=expected_definition_version,
            members=members,
            actor_id=actor_id,
        )

    async def unlink_member(
        self,
        collection_id: str,
        member_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        collection = await self.get_collection(collection_id, org_id)
        self._require_owner(collection, actor_id)
        return await self._repository.unlink_member(
            collection_id,
            member_id,
            org_id,
            expected_definition_version=expected_definition_version,
            actor_id=actor_id,
        )

    async def unlink_member_for_automation(
        self,
        collection_id: str,
        member_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        await self.get_collection(collection_id, org_id)
        return await self._repository.unlink_member(
            collection_id,
            member_id,
            org_id,
            expected_definition_version=expected_definition_version,
            actor_id=actor_id,
        )

    async def replace_members(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        collection = await self.get_collection(collection_id, org_id)
        self._require_owner(collection, actor_id)
        self._validate_supported_member_specs(members)
        self._validate_positions(tuple(item.position for item in members))
        await self._validate_members(
            collection, tuple(item.source_dataset_id for item in members)
        )
        return await self._repository.replace_members(
            collection_id,
            org_id,
            expected_definition_version=expected_definition_version,
            members=members,
            actor_id=actor_id,
        )

    async def create_revision(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        trigger_kind: str,
        trigger_ref: str | None,
    ) -> DatasetCollectionRevision:
        collection = await self.get_collection(collection_id, org_id)
        self._require_owner(collection, actor_id)
        return await self._publish_snapshot(
            collection,
            org_id=org_id,
            actor_id=actor_id,
            expected_definition_version=expected_definition_version,
            trigger_kind=trigger_kind,
            trigger_ref=trigger_ref,
        )

    async def get_snapshot_update_status(
        self,
        collection_id: str,
        org_id: str,
    ) -> CollectionSnapshotUpdateStatus:
        await self.get_collection(collection_id, org_id)
        snapshot = await self._repository.get_current_revision(collection_id, org_id)
        if snapshot is None:
            return CollectionSnapshotUpdateStatus(
                snapshot_id=None,
                snapshot_revision_number=None,
                update_available=False,
                outdated_member_count=0,
                members=(),
            )
        entries = tuple(
            _snapshot_revision_entry(item) for item in snapshot.source_snapshot
        )
        dataset_ids = tuple(entry[1] for entry in entries)
        current_revisions = await self._dataset_revision_reader.list_current(
            dataset_ids,
            org_id,
        )
        members = tuple(
            CollectionSnapshotMemberUpdate(
                member_id=member_id,
                dataset_id=dataset_id,
                observed_dataset_revision_id=observed_id,
                observed_dataset_revision_number=observed_number,
                current_dataset_revision_id=(
                    current_revisions[dataset_id].id
                    if dataset_id in current_revisions
                    else None
                ),
                current_dataset_revision_number=(
                    current_revisions[dataset_id].revision_number
                    if dataset_id in current_revisions
                    else None
                ),
                update_available=(
                    dataset_id in current_revisions
                    and current_revisions[dataset_id].id != observed_id
                ),
            )
            for member_id, dataset_id, observed_id, observed_number in entries
        )
        outdated_member_count = sum(item.update_available for item in members)
        return CollectionSnapshotUpdateStatus(
            snapshot_id=snapshot.id,
            snapshot_revision_number=snapshot.revision_number,
            update_available=outdated_member_count > 0,
            outdated_member_count=outdated_member_count,
            members=members,
        )

    async def refresh_snapshot(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
    ) -> CollectionSnapshotRefreshResult:
        collection = await self.get_collection(collection_id, org_id)
        self._require_owner(collection, actor_id)
        current = await self._repository.get_current_revision(collection_id, org_id)
        snapshot = await self._publish_snapshot(
            collection,
            org_id=org_id,
            actor_id=actor_id,
            expected_definition_version=expected_definition_version,
            trigger_kind="dataset_revision_refresh",
            trigger_ref=current.id if current is not None else None,
        )
        return CollectionSnapshotRefreshResult(
            outcome=(
                "unchanged"
                if current is not None and snapshot.id == current.id
                else "refreshed"
            ),
            snapshot=snapshot,
        )

    async def publish_snapshot_for_automation(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        trigger_kind: str,
        trigger_ref: str | None,
    ) -> DatasetCollectionRevision:
        collection = await self.get_collection(collection_id, org_id)
        return await self._publish_snapshot(
            collection,
            org_id=org_id,
            actor_id=actor_id,
            expected_definition_version=expected_definition_version,
            trigger_kind=trigger_kind,
            trigger_ref=trigger_ref,
        )

    async def _publish_snapshot(
        self,
        collection: DatasetCollection,
        *,
        org_id: str,
        actor_id: str,
        expected_definition_version: int,
        trigger_kind: str,
        trigger_ref: str | None,
    ) -> DatasetCollectionRevision:
        if collection.definition_version != expected_definition_version:
            from app.modules.dataset_collections.domain.errors import (
                DatasetCollectionConflictError,
            )

            raise DatasetCollectionConflictError(
                "definition_version_conflict",
                "Collection definition changed; reload before creating a revision",
            )
        members = await self.list_members(collection.id, org_id)
        if not members:
            raise DatasetCollectionValidationError(
                "no_active_members",
                "Cannot create a collection revision without active members",
            )
        datasets = await self._datasets_for_member_ids(
            tuple(item.source_dataset_id for item in members), org_id
        )
        dataset_revisions = await self._dataset_revisions_for_members(
            members,
            org_id=org_id,
            actor_id=actor_id,
        )
        definition_payload = {
            "collection_id": collection.id,
            "definition_version": collection.definition_version,
            "target_view_contract": collection.target_view_contract,
            "target_schema_version": collection.target_schema_version,
            "duplicate_policy": collection.duplicate_policy,
            "missing_data_policy": collection.missing_data_policy,
            "members": [
                {
                    "member_id": member.id,
                    "source_dataset_id": member.source_dataset_id,
                    "position": member.position,
                    "filter_spec": member.filter_spec,
                    "label_mapping": member.label_mapping,
                    "sampling_spec": member.sampling_spec,
                    "dataset_revision_id": dataset_revisions[
                        member.source_dataset_id
                    ].id,
                }
                for member in members
            ],
        }
        definition_hash = hashlib.sha256(
            json.dumps(
                definition_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        snapshot: tuple[dict[str, object], ...] = tuple(
            self._snapshot_member(
                collection=collection,
                member=member,
                dataset=datasets[member.source_dataset_id],
                dataset_revision=dataset_revisions[member.source_dataset_id],
            )
            for member in members
        )
        row_count = await self._snapshot_row_count(tuple(dataset_revisions.values()))
        current = await self._repository.get_current_revision(collection.id, org_id)
        if current is not None and current.definition_hash == definition_hash:
            return current

        revision_id = str(uuid4())
        revision_number = await self._repository.next_revision_number(
            collection.id, org_id
        )
        manifest_payload = {
            "manifest_format": _COMPOSITE_MANIFEST_FORMAT,
            "collection_id": collection.id,
            "collection_revision_id": revision_id,
            "collection_revision_number": revision_number,
            "definition_version": collection.definition_version,
            "definition_hash": definition_hash,
            "target": {
                "view_id": collection.target_view_id,
                "view_contract": collection.target_view_contract,
                "schema_version": collection.target_schema_version,
            },
            "duplicate_policy": collection.duplicate_policy,
            "missing_data_policy": collection.missing_data_policy,
            "source_resolution": "observed",
            "reproducibility": {
                "capability": False,
                "reason": (
                    "Dataset Revision references are audit observations; runtimes "
                    "resolve each member's current data when execution starts"
                ),
            },
            "rule_versions": [],
            "members": list(snapshot),
            "summary": {"row_count": row_count, "label_counts": {}},
        }
        manifest_uri = await self._artifact_storage.put_bytes(
            (
                f"dataset-collections/{collection.id}/revisions/"
                f"{revision_id}/manifest.json"
            ),
            json.dumps(
                manifest_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            "application/json",
        )
        revision = DatasetCollectionRevision(
            id=revision_id,
            collection_id=collection.id,
            revision_number=revision_number,
            definition_version=collection.definition_version,
            definition_hash=definition_hash,
            target_view_id=collection.target_view_id,
            target_view_contract=collection.target_view_contract,
            target_schema_version=collection.target_schema_version,
            status="ready",
            source_snapshot=snapshot,
            row_count=row_count,
            label_counts={},
            manifest_uri=manifest_uri,
            provenance_uri=None,
            trigger_kind=trigger_kind,
            trigger_ref=trigger_ref,
            created_by=actor_id,
            created_at=_utcnow(),
            error_code=None,
            error_detail=None,
            manifest_format=_COMPOSITE_MANIFEST_FORMAT,
            source_resolution="observed",
            reproducibility_capability=False,
        )
        try:
            return await self._repository.create_revision(
                revision,
                org_id,
                expected_definition_version=expected_definition_version,
            )
        except Exception:
            await asyncio.gather(
                self._artifact_storage.delete(manifest_uri),
                return_exceptions=True,
            )
            raise

    async def list_revisions(
        self, collection_id: str, org_id: str
    ) -> list[DatasetCollectionRevision]:
        return await self._repository.list_revisions(collection_id, org_id)

    async def get_revision(
        self, collection_id: str, revision_id: str, org_id: str
    ) -> DatasetCollectionRevision:
        revision = await self._repository.get_revision(
            collection_id, revision_id, org_id
        )
        if revision is None:
            raise DatasetCollectionNotFoundError("Collection revision not found")
        return revision

    async def has_dataset_references(self, dataset_id: str, org_id: str) -> bool:
        return await self._repository.has_dataset_references(dataset_id, org_id)

    async def _validate_members(
        self, collection: DatasetCollection, dataset_ids: tuple[str, ...]
    ) -> None:
        if len(dataset_ids) != len(set(dataset_ids)):
            raise DatasetCollectionValidationError(
                "duplicate_dataset", "A dataset may occur only once in a collection"
            )
        datasets = await self._datasets_for_member_ids(dataset_ids, collection.org_id)
        label_spaces: dict[str, tuple[str, ...]] = {}
        for dataset_id, dataset in datasets.items():
            if collection.target_view_id not in dataset.view_types:
                raise DatasetCollectionValidationError(
                    "incompatible_view",
                    f"Dataset '{dataset_id}' does not provide target view "
                    f"'{collection.target_view_id}'",
                )
            label_spaces[dataset_id] = tuple(dataset.task_spec.label_space)
        distinct_spaces = set(label_spaces.values())
        if len(distinct_spaces) > 1:
            raise DatasetCollectionValidationError(
                "label_space_mismatch",
                "MVP collections require identical ordered label spaces",
            )

    async def _datasets_for_member_ids(
        self, dataset_ids: tuple[str, ...], org_id: str
    ) -> dict[str, Dataset]:
        results = await asyncio.gather(
            *(
                self._dataset_reader.get_dataset(dataset_id, org_id=org_id)
                for dataset_id in dataset_ids
            )
        )
        datasets: dict[str, Dataset] = {}
        for dataset_id, dataset in zip(dataset_ids, results, strict=True):
            if dataset is None or dataset.org_id != org_id:
                raise DatasetCollectionValidationError(
                    "dataset_not_found",
                    f"Dataset '{dataset_id}' was not found in this organization",
                )
            datasets[dataset_id] = dataset
        return datasets

    async def _dataset_revisions_for_members(
        self,
        members: list[DatasetCollectionMember],
        *,
        org_id: str,
        actor_id: str,
    ) -> dict[str, DatasetRevision]:
        dataset_ids = tuple(member.source_dataset_id for member in members)
        current = await self._dataset_revision_reader.list_current(dataset_ids, org_id)
        missing = tuple(
            member for member in members if member.source_dataset_id not in current
        )
        baselines = await asyncio.gather(
            *(
                self._dataset_revision_reader.resolve_or_create_baseline(
                    dataset_id=member.source_dataset_id,
                    org_id=org_id,
                    created_by=actor_id,
                )
                for member in missing
            )
        )
        return {
            **current,
            **{
                member.source_dataset_id: revision
                for member, revision in zip(missing, baselines, strict=True)
            },
        }

    async def _snapshot_row_count(
        self,
        revisions: tuple[DatasetRevision, ...],
    ) -> int | None:
        documents = await asyncio.gather(
            *(
                self._artifact_storage.get_bytes(revision.manifest_uri)
                for revision in revisions
            )
        )
        counts: list[int] = []
        for raw in documents:
            document = json.loads(raw)
            artifact = document.get("artifact")
            if not isinstance(artifact, dict):
                return None
            count = artifact.get("row_count")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                return None
            counts.append(count)
        return sum(counts)

    @staticmethod
    def _snapshot_member(
        *,
        collection: DatasetCollection,
        member: DatasetCollectionMember,
        dataset: Dataset,
        dataset_revision: DatasetRevision,
    ) -> dict[str, object]:
        return {
            "member_id": member.id,
            "source_dataset_id": member.source_dataset_id,
            "position": member.position,
            "dataset_revision_id": dataset_revision.id,
            "dataset_revision_number": dataset_revision.revision_number,
            "dataset_revision_manifest_uri": dataset_revision.manifest_uri,
            "dataset_revision_binding": "observed",
            "dataset_revision_reproducible": False,
            "collection_definition_version": collection.definition_version,
            "filter_version": _plan_version(member.filter_spec),
            "filter_spec": member.filter_spec,
            "mapping_version": _plan_version(member.label_mapping),
            "label_mapping": member.label_mapping,
            "sampling_version": _plan_version(member.sampling_spec),
            "sampling_spec": member.sampling_spec,
            "storage_mode": dataset.storage_mode.value,
            "dataset_type": dataset.dataset_type,
            "view_types": list(dataset.view_types),
            "label_space": list(dataset.task_spec.label_space),
            "image_source": (
                dataset.image_source.model_dump(mode="json")
                if dataset.image_source is not None
                else None
            ),
        }

    @staticmethod
    def _validate_positions(positions: tuple[int, ...]) -> None:
        if len(positions) != len(set(positions)):
            raise DatasetCollectionValidationError(
                "duplicate_position",
                "Active collection member positions must be unique",
            )

    @staticmethod
    def _validate_supported_member_specs(
        members: tuple[NewCollectionMember, ...],
    ) -> None:
        if any(
            member.filter_spec or member.label_mapping or member.sampling_spec
            for member in members
        ):
            raise DatasetCollectionValidationError(
                "unsupported_member_transform",
                "Member filters, label mappings, and sampling are not supported yet",
            )

    @staticmethod
    def _require_owner(collection: DatasetCollection, actor_id: str) -> None:
        if collection.created_by != actor_id:
            raise DatasetCollectionPermissionError(
                "Only the collection creator can modify this collection"
            )


def _plan_version(plan: dict[str, object] | dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _snapshot_revision_entry(
    item: dict[str, object],
) -> tuple[str, str, str | None, int | None]:
    member_id = item.get("member_id")
    dataset_id = item.get("source_dataset_id")
    if not isinstance(member_id, str) or not member_id:
        raise DatasetCollectionValidationError(
            "invalid_snapshot_provenance",
            "Snapshot member provenance is missing member_id",
        )
    if not isinstance(dataset_id, str) or not dataset_id:
        raise DatasetCollectionValidationError(
            "invalid_snapshot_provenance",
            "Snapshot member provenance is missing source_dataset_id",
        )
    observed_id = item.get("dataset_revision_id")
    observed_number = item.get("dataset_revision_number")
    return (
        member_id,
        dataset_id,
        observed_id if isinstance(observed_id, str) and observed_id else None,
        (
            observed_number
            if isinstance(observed_number, int)
            and not isinstance(observed_number, bool)
            else None
        ),
    )
