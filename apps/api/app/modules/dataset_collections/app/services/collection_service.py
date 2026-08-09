from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import uuid4

import polars as pl
from injector import inject

from app.modules.dataset_collections.domain.errors import (
    DatasetCollectionNotFoundError,
    DatasetCollectionPermissionError,
    DatasetCollectionValidationError,
)
from app.modules.dataset_collections.domain.models import (
    DatasetCollection,
    DatasetCollectionMember,
    DatasetCollectionRevision,
    NewCollectionMember,
)
from app.modules.dataset_collections.domain.repository import (
    DatasetCollectionRepository,
)
from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.types.catalog import get_view_meta
from app.shared.api.schemas import Dataset
from app.shared.domain.protocols import ArtifactStorage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DatasetCollectionService:
    @inject
    def __init__(
        self,
        repository: DatasetCollectionRepository,
        dataset_reader: DatasetReader,
        storage_factory: DatasetStorageFactoryPort,
        artifact_storage: ArtifactStorage,
    ) -> None:
        self._repository = repository
        self._dataset_reader = dataset_reader
        self._storage_factory = storage_factory
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
        self, org_id: str, *, offset: int, limit: int
    ) -> tuple[list[DatasetCollection], int]:
        return await self._repository.list_collections(
            org_id, offset=offset, limit=limit
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
        if not await self._repository.delete_collection(collection_id, org_id):
            raise DatasetCollectionNotFoundError("Dataset collection not found")

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
        self._validate_supported_member_specs(members)
        existing = await self._repository.list_active_members(collection_id, org_id)
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
            collection_id,
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
        if collection.definition_version != expected_definition_version:
            from app.modules.dataset_collections.domain.errors import (
                DatasetCollectionConflictError,
            )

            raise DatasetCollectionConflictError(
                "definition_version_conflict",
                "Collection definition changed; reload before creating a revision",
            )
        members = await self.list_members(collection_id, org_id)
        if not members:
            raise DatasetCollectionValidationError(
                "no_active_members",
                "Cannot create a collection revision without active members",
            )
        datasets = await self._datasets_for_member_ids(
            tuple(item.source_dataset_id for item in members), org_id
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
        revision_id = str(uuid4())
        (
            data_uri,
            provenance_uri,
            row_count,
            label_counts,
        ) = await self._materialize_revision(
            collection=collection,
            revision_id=revision_id,
            members=members,
            datasets=datasets,
        )
        snapshot: tuple[dict[str, object], ...] = tuple(
            cast(
                dict[str, object],
                {
                    "member_id": member.id,
                    "source_dataset_id": member.source_dataset_id,
                    "position": member.position,
                    "storage_mode": datasets[
                        member.source_dataset_id
                    ].storage_mode.value,
                    "dataset_type": datasets[member.source_dataset_id].dataset_type,
                    "view_types": list(datasets[member.source_dataset_id].view_types),
                    "label_space": list(
                        datasets[member.source_dataset_id].task_spec.label_space
                    ),
                },
            )
            for member in members
        )
        revision = DatasetCollectionRevision(
            id=revision_id,
            collection_id=collection.id,
            revision_number=await self._repository.next_revision_number(
                collection.id, org_id
            ),
            definition_version=collection.definition_version,
            definition_hash=definition_hash,
            target_view_id=collection.target_view_id,
            target_view_contract=collection.target_view_contract,
            target_schema_version=collection.target_schema_version,
            status="ready",
            source_snapshot=snapshot,
            row_count=row_count,
            label_counts=label_counts,
            manifest_uri=data_uri,
            provenance_uri=provenance_uri,
            trigger_kind=trigger_kind,
            trigger_ref=trigger_ref,
            created_by=actor_id,
            created_at=_utcnow(),
            error_code=None,
            error_detail=None,
        )
        try:
            return await self._repository.create_revision(
                revision,
                org_id,
                expected_definition_version=expected_definition_version,
            )
        except Exception:
            await asyncio.gather(
                self._artifact_storage.delete(data_uri),
                self._artifact_storage.delete(provenance_uri),
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

    async def _materialize_revision(
        self,
        *,
        collection: DatasetCollection,
        revision_id: str,
        members: list[DatasetCollectionMember],
        datasets: dict[str, Dataset],
    ) -> tuple[str, str, int, dict[str, int]]:
        frames: list[pl.LazyFrame] = []
        expected_columns: tuple[str, ...] | None = None
        for member in members:
            dataset = datasets[member.source_dataset_id]
            storage = await self._storage_factory.open(dataset.id, collection.org_id)
            rows = cast(
                pl.LazyFrame,
                await storage.list_samples(
                    return_lazyframe=True,
                    with_labels=True,
                    with_predictions=False,
                ),
            )
            rows = _normalize_storage_rows(rows)
            columns = tuple(rows.collect_schema().names())
            if "sample_id" not in columns:
                raise DatasetCollectionValidationError(
                    "missing_sample_identity",
                    f"Dataset '{dataset.id}' does not expose sample_id",
                )
            if expected_columns is None:
                expected_columns = columns
            elif columns != expected_columns:
                raise DatasetCollectionValidationError(
                    "incompatible_schema",
                    "Collection members do not expose an identical storage view schema",
                )
            source_sample = pl.col("sample_id").cast(pl.String)
            row_key = pl.concat_str([pl.lit(dataset.id), source_sample], separator="::")
            frames.append(
                rows.with_columns(
                    source_sample.alias("source_sample_id"),
                    pl.lit(dataset.id).alias("source_dataset_id"),
                    pl.lit(member.id).alias("collection_member_id"),
                    row_key.alias("row_key"),
                ).with_columns(pl.col("row_key").alias("sample_id"))
            )
        combined = pl.concat(frames, how="vertical")
        with tempfile.TemporaryDirectory(prefix="dataset-collection-revision-") as tmp:
            root = Path(tmp)
            data_path = root / "data.parquet"
            provenance_path = root / "provenance.parquet"
            await asyncio.to_thread(
                combined.sink_parquet,
                data_path,
                compression="zstd",
                maintain_order=True,
            )
            await asyncio.to_thread(
                combined.select(
                    pl.col("row_key").alias("output_row_id"),
                    "source_dataset_id",
                    "source_sample_id",
                    "collection_member_id",
                ).sink_parquet,
                provenance_path,
                compression="zstd",
                maintain_order=True,
            )
            summary = pl.scan_parquet(data_path)
            row_count = int(
                (await summary.select(pl.len().alias("count")).collect_async()).item()
            )
            label_counts: dict[str, int] = {}
            if "label" in summary.collect_schema().names():
                counts = (
                    summary.filter(pl.col("label").is_not_null())
                    .group_by("label")
                    .agg(pl.len().alias("count"))
                    .collect_async()
                )
                counts = await counts
                label_counts = {
                    str(label): int(count) for label, count in counts.iter_rows()
                }
            data_uri, provenance_uri = await asyncio.gather(
                self._artifact_storage.put_file(
                    f"dataset-collections/{collection.id}/revisions/{revision_id}/data.parquet",
                    str(data_path),
                    "application/vnd.apache.parquet",
                ),
                self._artifact_storage.put_file(
                    f"dataset-collections/{collection.id}/revisions/{revision_id}/provenance.parquet",
                    str(provenance_path),
                    "application/vnd.apache.parquet",
                ),
            )
        return data_uri, provenance_uri, row_count, label_counts

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


def _normalize_storage_rows(rows: pl.LazyFrame) -> pl.LazyFrame:
    schema = rows.collect_schema()
    columns = schema.names()
    if "sample_id" in columns:
        return rows
    if "id" not in columns:
        return rows
    expressions: list[pl.Expr] = [pl.col("id").cast(pl.String).alias("sample_id")]
    expressions.extend(
        pl.col(column)
        for column in columns
        if column not in {"id", "dataset_id", "metadata_json"}
    )
    metadata_dtype = schema.get("metadata_json")
    if isinstance(metadata_dtype, pl.Struct):
        # Collection provenance uses the platform sample identity.  An SC
        # upstream ``sample_id`` in metadata must not shadow that identity.
        existing = set(columns) | {"sample_id"}
        expressions.extend(
            pl.col("metadata_json").struct.field(field.name).alias(field.name)
            for field in metadata_dtype.fields
            if field.name not in existing
        )
    return rows.select(expressions)
