from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.dataset_collections.domain.models import (
    DatasetCollection,
    DatasetCollectionMember,
    DatasetCollectionRevision,
    NewCollectionMember,
)
from app.modules.dataset_collections.port.local import (
    CollectionAutomationAdmissionPort,
    CollectionRevisionPublishingPort,
)
from app.modules.source_discovery.adapter.sql_repository import (
    SourceDiscoverySqlRepository,
)
from app.modules.source_discovery.app.services.collection_discovery_poller import (
    CollectionDiscoveryPoller,
)
from app.modules.source_discovery.app.services.source_discovery_service import (
    SourceDiscoveryService,
)
from app.modules.source_discovery.domain.models import (
    DiscoveryRun,
    FilterCombinator,
    FilterGroup,
    FilterOperator,
    FilterPredicate,
    ImportProfileVersion,
    SourceConnector,
    SourceDiscoveryBatch,
    SourceEstimate,
    SourceFieldType,
    SourceFilterField,
    SourceImportResult,
    SourceProviderDescriptor,
    SourceRecord,
)
from app.modules.source_discovery.domain.errors import (
    SourceDiscoveryConflictError,
    SourceDiscoveryValidationError,
)
from app.modules.source_discovery.domain.provider import SourceProviderCatalog
from app.shared.db.base import Base
from app.shared.db.session import create_engine, create_session_factory


def _now() -> datetime:
    return datetime.now(UTC)


def _record(key: str) -> SourceRecord:
    index = int(key.removeprefix("record-"))
    return SourceRecord(
        record_key=key,
        observed_at=datetime(2026, 8, 15, index, tzinfo=UTC),
        display_name=f"Dataset {key}",
        attributes={"layer": "M1", "index": index},
    )


class _Provider:
    descriptor = SourceProviderDescriptor(
        provider_id="test",
        display_name="Test source",
        fields=(
            SourceFilterField(
                key="layer",
                label="Layer",
                field_type=SourceFieldType.STRING,
                operators=(FilterOperator.EQ,),
            ),
        ),
        backfill_time_field="observed_at",
        max_condition_depth=4,
        max_condition_nodes=20,
    )

    def __init__(self, records: tuple[SourceRecord, ...]) -> None:
        self.records = records
        self.publication_times: dict[str, datetime] = {
            record.record_key: record.observed_at for record in records
        }
        self.fail_keys: set[str] = set()
        self.imports: list[tuple[str, str]] = []
        self.require_streaming_consumption = False
        self.fail_live_after_batches: int | None = None

    async def discover_live(
        self,
        *,
        connector: SourceConnector,
        condition: FilterGroup,
        publication_start_utc: datetime,
        publication_end_utc: datetime,
        after_cursor: dict[str, object] | None,
    ) -> AsyncIterator[SourceDiscoveryBatch]:
        del connector, condition
        after_position = (
            str(after_cursor["position"])
            if after_cursor is not None
            else None
        )
        ordered = sorted(
            (
                (self.publication_times[record.record_key], record.record_key, record)
                for record in self.records
                if publication_start_utc
                <= self.publication_times[record.record_key]
                < publication_end_utc
            ),
            key=lambda item: (item[0], item[1]),
        )
        if after_position is not None:
            positions = [record_key for _, record_key, _ in ordered]
            ordered = ordered[positions.index(after_position) + 1 :]
        for index, (_, record_key, record) in enumerate(ordered):
            if self.fail_live_after_batches == index:
                raise RuntimeError("live provider failed")
            yield SourceDiscoveryBatch(
                records=(record,),
                checkpoint={"position": record_key},
            )

    async def discover_backfill(
        self,
        *,
        connector: SourceConnector,
        condition: FilterGroup,
        start_utc: datetime,
        end_utc: datetime,
    ) -> AsyncIterator[SourceDiscoveryBatch]:
        del connector, condition
        matched = tuple(
            record
            for record in self.records
            if start_utc <= record.observed_at < end_utc
        )
        for index, record in enumerate(matched):
            if self.require_streaming_consumption:
                assert len(self.imports) == index
            yield SourceDiscoveryBatch(records=(record,), checkpoint=None)

    async def estimate(
        self,
        *,
        connector: SourceConnector,
        condition: FilterGroup,
        start_utc: datetime,
        end_utc: datetime,
        representative_limit: int,
    ) -> SourceEstimate:
        records: list[SourceRecord] = []
        async for batch in self.discover_backfill(
            connector=connector,
            condition=condition,
            start_utc=start_utc,
            end_utc=end_utc,
        ):
            records.extend(batch.records)
        return SourceEstimate(
            as_of_utc=_now(),
            matched_count=len(records),
            representative_records=tuple(records[:representative_limit]),
        )

    async def import_record(
        self,
        *,
        connector: SourceConnector,
        profile: ImportProfileVersion,
        record: SourceRecord,
        org_id: str,
        actor_id: str,
    ) -> SourceImportResult:
        del connector, profile, actor_id
        if record.record_key in self.fail_keys:
            raise RuntimeError(f"cannot import {record.record_key}")
        dataset_id = f"{org_id}-{record.record_key}-{len(self.imports) + 1}"
        self.imports.append((record.record_key, dataset_id))
        return SourceImportResult(
            dataset_id=dataset_id,
            dataset_name=record.display_name,
            imported_count=1,
        )


class _Collections:
    def __init__(self, collection_id: str, org_id: str) -> None:
        now = _now()
        self.collection = DatasetCollection(
            id=collection_id,
            org_id=org_id,
            name=collection_id,
            description="",
            target_view_id="patch_image_v1",
            target_view_contract="sc.patch",
            target_schema_version="1",
            duplicate_policy="keep_all",
            missing_data_policy="fail",
            definition_version=0,
            created_by="actor",
            created_at=now,
            updated_at=now,
        )
        self.members: list[DatasetCollectionMember] = []
        self.link_calls = 0

    async def get_collection(self, collection_id: str, org_id: str) -> DatasetCollection:
        assert collection_id == self.collection.id and org_id == self.collection.org_id
        return self.collection

    async def list_members(
        self, collection_id: str, org_id: str
    ) -> list[DatasetCollectionMember]:
        await self.get_collection(collection_id, org_id)
        return list(self.members)

    async def admit_members_for_automation(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        await self.get_collection(collection_id, org_id)
        assert expected_definition_version == self.collection.definition_version
        self.link_calls += 1
        new_version = self.collection.definition_version + 1
        now = _now()
        for item in members:
            self.members.append(
                DatasetCollectionMember(
                    id=str(uuid4()),
                    collection_id=collection_id,
                    source_dataset_id=item.source_dataset_id,
                    position=item.position,
                    linked_definition_version=new_version,
                    unlinked_definition_version=None,
                    filter_spec=item.filter_spec,
                    label_mapping=item.label_mapping,
                    sampling_spec=item.sampling_spec,
                    linked_by=actor_id,
                    linked_at=now,
                    unlinked_by=None,
                    unlinked_at=None,
                )
            )
        self.collection = replace(
            self.collection,
            definition_version=new_version,
            updated_at=now,
        )
        return self.collection, list(self.members)

    async def unlink_member_for_automation(
        self,
        collection_id: str,
        member_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        del actor_id
        await self.get_collection(collection_id, org_id)
        assert expected_definition_version == self.collection.definition_version
        self.members = [member for member in self.members if member.id != member_id]
        self.collection = replace(
            self.collection,
            definition_version=self.collection.definition_version + 1,
            updated_at=_now(),
        )
        return self.collection, list(self.members)


class _Revisions:
    def __init__(self, collections: _Collections) -> None:
        self.collections = collections
        self.calls = 0
        self.fail = False

    async def create_revision_for_automation(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        trigger_kind: str,
        trigger_ref: str | None,
    ) -> DatasetCollectionRevision:
        del actor_id, trigger_kind, trigger_ref
        collection = await self.collections.get_collection(collection_id, org_id)
        assert expected_definition_version == collection.definition_version
        self.calls += 1
        if self.fail:
            raise RuntimeError("revision unavailable")
        return DatasetCollectionRevision(
            id=f"revision-{self.calls}",
            collection_id=collection_id,
            revision_number=self.calls,
            definition_version=collection.definition_version,
            definition_hash=f"hash-{self.calls}",
            target_view_id=collection.target_view_id,
            target_view_contract=collection.target_view_contract,
            target_schema_version=collection.target_schema_version,
            status="ready",
            members=(),
            manifest_uri=None,
            trigger_kind="discovery",
            trigger_ref=None,
            created_by="actor",
            created_at=_now(),
            error_code=None,
            error_detail=None,
        )


async def _service(
    provider: _Provider,
    collections: _Collections,
) -> tuple[SourceDiscoveryService, SourceDiscoverySqlRepository, AsyncEngine]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SourceDiscoverySqlRepository(create_session_factory(engine))
    revisions = _Revisions(collections)
    service = SourceDiscoveryService(
        repository=repository,
        providers=SourceProviderCatalog((provider,)),
        collections=cast(CollectionAutomationAdmissionPort, collections),
        revision_publisher=cast(CollectionRevisionPublishingPort, revisions),
    )
    return service, repository, engine


async def _configured_rule(
    service: SourceDiscoveryService,
    *,
    collection_id: str,
    org_id: str,
) -> tuple[str, str, str]:
    connector = await service.create_connector(
        org_id=org_id,
        actor_id="actor",
        provider_id="test",
        name=f"connector-{collection_id}",
        config={},
    )
    profile = await service.create_import_profile(
        org_id=org_id,
        actor_id="actor",
        connector_id=connector.id,
        name="bounded",
        settings={},
    )
    condition = FilterGroup(
        combinator=FilterCombinator.ALL,
        children=(
            FilterPredicate(
                field="layer",
                operator=FilterOperator.EQ,
                value="M1",
            ),
        ),
    )
    rule, _ = await service.create_rule(
        collection_id=collection_id,
        org_id=org_id,
        actor_id="actor",
        name="M1 records",
        connector_id=connector.id,
        import_profile_version_id=profile.id,
        condition=condition,
    )
    return connector.id, profile.id, rule.id


@pytest.mark.asyncio
async def test_import_profiles_can_be_listed_for_rule_setup() -> None:
    service, _, engine = await _service(_Provider(()), _Collections("collection", "org"))
    try:
        connector = await service.create_connector(
            org_id="org",
            actor_id="actor",
            provider_id="test",
            name="SC source",
            config={},
        )
        profile = await service.create_import_profile(
            org_id="org",
            actor_id="actor",
            connector_id=connector.id,
            name="Bounded import",
            settings={},
        )

        listed = await service.list_import_profiles(connector.id, "org")

        assert [item.id for item in listed] == [profile.id]
        assert not hasattr(profile, "max_records_per_run")
        assert not hasattr(profile, "max_rows_per_dataset")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sc_partition_creates_exact_rule_and_rejects_duplicate_assignment() -> None:
    provider = _Provider(())
    provider.descriptor = replace(
        provider.descriptor,
        provider_id="sc",
        fields=(
            SourceFilterField(
                key="layer_id",
                label="Layer",
                field_type=SourceFieldType.STRING,
                operators=(FilterOperator.EQ,),
            ),
            SourceFilterField(
                key="device",
                label="Device",
                field_type=SourceFieldType.STRING,
                operators=(FilterOperator.EQ,),
            ),
        ),
    )
    service, _, engine = await _service(provider, _Collections("collection", "org"))
    try:
        connector = await service.create_connector(
            org_id="org",
            actor_id="actor",
            provider_id="sc",
            name="SC source",
            config={},
        )
        profile = await service.create_import_profile(
            org_id="org",
            actor_id="actor",
            connector_id=connector.id,
            name="Bounded import",
            settings={},
        )

        rule, version, partition = await service.create_sc_partition(
            collection_id="collection",
            org_id="org",
            actor_id="actor",
            name="M1 device A",
            connector_id=connector.id,
            import_profile_version_id=profile.id,
            layer_id="M1",
            device="DEVICE-A",
        )

        assert partition.rule_id == rule.id == version.rule_id
        assert partition.layer_id == "M1"
        assert partition.device == "DEVICE-A"
        assert version.condition == FilterGroup(
            combinator=FilterCombinator.ALL,
            children=(
                FilterPredicate("layer_id", FilterOperator.EQ, "M1"),
                FilterPredicate("device", FilterOperator.EQ, "DEVICE-A"),
            ),
        )
        assert await service.list_sc_partitions("collection", "org") == [partition]

        with pytest.raises(
            SourceDiscoveryConflictError, match="cannot change their source"
        ):
            await service.create_rule_version(
                collection_id="collection",
                rule_id=rule.id,
                org_id="org",
                actor_id="actor",
                connector_id=connector.id,
                import_profile_version_id=profile.id,
                condition=FilterGroup(
                    combinator=FilterCombinator.ALL,
                    children=(
                        FilterPredicate("layer_id", FilterOperator.EQ, "M1"),
                        FilterPredicate("device", FilterOperator.EQ, "DEVICE-B"),
                    ),
                ),
            )

        with pytest.raises(SourceDiscoveryConflictError, match="already assigned"):
            await service.create_sc_partition(
                collection_id="collection",
                org_id="org",
                actor_id="actor",
                name="duplicate",
                connector_id=connector.id,
                import_profile_version_id=profile.id,
                layer_id="M1",
                device="DEVICE-A",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_live_discovery_records_overlap_as_skipped() -> None:
    org_id = "org"
    collections = _Collections("collection-a", org_id)
    service, repository, engine = await _service(_Provider(()), collections)
    try:
        _, _, rule_id = await _configured_rule(
            service, collection_id=collections.collection.id, org_id=org_id
        )
        rule, version = (await repository.list_rules("collection-a", org_id))[0]
        active = await repository.create_run(
            DiscoveryRun(
                id=str(uuid4()),
                org_id=org_id,
                collection_id=collections.collection.id,
                rule_id=rule_id,
                rule_version_id=version.id,
                kind="live",
                status="running",
                as_of_utc=rule.activated_at + timedelta(minutes=1),
                range_start_utc=rule.activated_at,
                range_end_utc=rule.activated_at + timedelta(minutes=1),
                timezone_name=None,
                parent_run_id=None,
                collection_revision_id=None,
                stats={},
                error_detail=None,
                created_by="system:collection-discovery",
                created_at=_now(),
                completed_at=None,
            )
        )

        execution = await service.run_live(
            collection_id=collections.collection.id,
            rule_id=rule_id,
            org_id=org_id,
            actor_id="system:collection-discovery",
            as_of_utc=rule.activated_at + timedelta(minutes=5),
        )

        assert execution.run.status == "skipped"
        assert execution.run.parent_run_id == active.id
        assert execution.run.stats == {"skipped": 1}
        assert "still has active run" in (execution.run.error_detail or "")
        stored_rule = await repository.get_rule(rule_id, "collection-a", org_id)
        assert stored_rule is not None
        assert stored_rule.live_cursor is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_live_discovery_finds_delayed_publication_once_and_checkpoints_last_record() -> None:
    org_id = "org"
    provider = _Provider(())
    collections = _Collections("collection-a", org_id)
    service, repository, engine = await _service(provider, collections)
    try:
        _, _, rule_id = await _configured_rule(
            service, collection_id=collections.collection.id, org_id=org_id
        )
        rule = await repository.get_rule(rule_id, "collection-a", org_id)
        assert rule is not None
        delayed = _record("record-1")
        provider.records = (delayed,)
        provider.publication_times = {
            delayed.record_key: rule.activated_at + timedelta(minutes=1)
        }

        first = await service.run_live(
            collection_id="collection-a",
            rule_id=rule_id,
            org_id=org_id,
            actor_id="system:collection-discovery",
            as_of_utc=rule.activated_at + timedelta(minutes=2),
        )
        replay = await service.run_live(
            collection_id="collection-a",
            rule_id=rule_id,
            org_id=org_id,
            actor_id="system:collection-discovery",
            as_of_utc=rule.activated_at + timedelta(minutes=3),
        )

        assert first.run.status == "completed"
        assert first.run.stats["imported"] == 1
        assert replay.run.status == "completed"
        assert replay.run.stats["scanned"] == 0
        assert len(provider.imports) == 1
        stored_rule = await repository.get_rule(rule_id, "collection-a", org_id)
        assert stored_rule is not None
        assert stored_rule.live_cursor == {"position": delayed.record_key}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_live_discovery_does_not_advance_checkpoint_after_provider_failure() -> None:
    org_id = "org"
    provider = _Provider(())
    collections = _Collections("collection-a", org_id)
    service, repository, engine = await _service(provider, collections)
    try:
        _, _, rule_id = await _configured_rule(
            service, collection_id=collections.collection.id, org_id=org_id
        )
        rule = await repository.get_rule(rule_id, "collection-a", org_id)
        assert rule is not None
        records = (_record("record-1"), _record("record-2"))
        provider.records = records
        provider.publication_times = {
            record.record_key: rule.activated_at + timedelta(minutes=1)
            for record in records
        }
        provider.fail_live_after_batches = 1

        failed = await service.run_live(
            collection_id="collection-a",
            rule_id=rule_id,
            org_id=org_id,
            actor_id="system:collection-discovery",
            as_of_utc=rule.activated_at + timedelta(minutes=2),
        )
        stored_rule = await repository.get_rule(rule_id, "collection-a", org_id)
        assert failed.run.status == "failed"
        assert stored_rule is not None and stored_rule.live_cursor is None

        provider.fail_live_after_batches = None
        recovered = await service.run_live(
            collection_id="collection-a",
            rule_id=rule_id,
            org_id=org_id,
            actor_id="system:collection-discovery",
            as_of_utc=rule.activated_at + timedelta(minutes=3),
        )

        assert recovered.run.status == "completed"
        assert len(provider.imports) == 2
        stored_rule = await repository.get_rule(rule_id, "collection-a", org_id)
        assert stored_rule is not None
        assert stored_rule.live_cursor == {"position": "record-2"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_collection_discovery_poller_runs_every_active_rule() -> None:
    org_id = "org"
    collections = _Collections("collection-a", org_id)
    service, repository, engine = await _service(_Provider(()), collections)
    try:
        await _configured_rule(
            service, collection_id=collections.collection.id, org_id=org_id
        )
        rule = (await repository.list_active_rules())[0]
        poller = CollectionDiscoveryPoller(repository, service)

        poll = await poller.poll_active_rules(
            as_of_utc=rule.activated_at + timedelta(minutes=5),
            actor_id="system:collection-discovery",
        )

        assert poll.as_of_utc == rule.activated_at + timedelta(minutes=5)
        assert len(poll.executions) == 1
        assert poll.executions[0].run.status == "completed"
        assert poll.executions[0].run.created_by == "system:collection-discovery"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_partial_retry_and_receipts_are_idempotent() -> None:
    org_id = "org"
    provider = _Provider((_record("record-1"), _record("record-2")))
    provider.fail_keys.add("record-2")
    collections = _Collections("collection-a", org_id)
    service, _, engine = await _service(provider, collections)
    revisions = cast(_Revisions, service._revision_publisher)
    try:
        _, _, rule_id = await _configured_rule(
            service, collection_id=collections.collection.id, org_id=org_id
        )
        start = datetime(2026, 8, 15, 0, tzinfo=UTC)
        end = start + timedelta(hours=3)
        first = await service.run_backfill(
            collection_id=collections.collection.id,
            rule_id=rule_id,
            org_id=org_id,
            actor_id="actor",
            start_utc=start,
            end_utc=end,
            timezone_name="Asia/Shanghai",
        )
        assert first.run.status == "partial"
        assert first.run.stats["linked"] == 1
        assert first.run.stats["failed"] == 1
        assert revisions.calls == 1

        provider.fail_keys.clear()
        retried = await service.retry_failed(
            run_id=first.run.id, org_id=org_id, actor_id="actor"
        )
        assert retried.run.status == "completed"
        assert retried.run.stats["linked"] == 1
        assert revisions.calls == 2

        replay = await service.run_backfill(
            collection_id=collections.collection.id,
            rule_id=rule_id,
            org_id=org_id,
            actor_id="actor",
            start_utc=start,
            end_utc=end,
            timezone_name="Asia/Shanghai",
        )
        assert replay.run.status == "completed"
        assert replay.run.stats["skipped"] == 2
        assert replay.run.collection_revision_id is None
        assert revisions.calls == 2
        assert collections.link_calls == 2
        assert len(provider.imports) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_consumes_every_discovery_batch_without_eager_collection() -> None:
    org_id = "org"
    provider = _Provider(
        (_record("record-1"), _record("record-2"), _record("record-3"))
    )
    provider.require_streaming_consumption = True
    collections = _Collections("collection-a", org_id)
    service, _, engine = await _service(provider, collections)
    try:
        _, _, rule_id = await _configured_rule(
            service, collection_id=collections.collection.id, org_id=org_id
        )
        execution = await service.run_backfill(
            collection_id=collections.collection.id,
            rule_id=rule_id,
            org_id=org_id,
            actor_id="actor",
            start_utc=datetime(2026, 8, 15, 0, tzinfo=UTC),
            end_utc=datetime(2026, 8, 15, 4, tzinfo=UTC),
            timezone_name="UTC",
        )

        assert execution.run.status == "completed"
        assert execution.run.stats["scanned"] == 3
        assert execution.run.stats["imported"] == 3
        assert [record_key for record_key, _ in provider.imports] == [
            "record-1",
            "record-2",
            "record-3",
        ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_same_source_is_not_shared_across_collections() -> None:
    org_id = "org"
    provider = _Provider((_record("record-1"),))
    first_collections = _Collections("collection-a", org_id)
    service, repository, engine = await _service(provider, first_collections)
    try:
        connector_id, profile_id, first_rule = await _configured_rule(
            service, collection_id="collection-a", org_id=org_id
        )
        start = datetime(2026, 8, 15, 0, tzinfo=UTC)
        end = start + timedelta(hours=2)
        await service.run_backfill(
            collection_id="collection-a",
            rule_id=first_rule,
            org_id=org_id,
            actor_id="actor",
            start_utc=start,
            end_utc=end,
            timezone_name="UTC",
        )

        second_collections = _Collections("collection-b", org_id)
        second_service = SourceDiscoveryService(
            repository=repository,
            providers=SourceProviderCatalog((provider,)),
            collections=cast(CollectionAutomationAdmissionPort, second_collections),
            revision_publisher=cast(
                CollectionRevisionPublishingPort, _Revisions(second_collections)
            ),
        )
        condition = FilterGroup(
            combinator=FilterCombinator.ALL,
            children=(
                FilterPredicate("layer", FilterOperator.EQ, "M1"),
            ),
        )
        second_rule, _ = await second_service.create_rule(
            collection_id="collection-b",
            org_id=org_id,
            actor_id="actor",
            name="same source",
            connector_id=connector_id,
            import_profile_version_id=profile_id,
            condition=condition,
        )
        await second_service.run_backfill(
            collection_id="collection-b",
            rule_id=second_rule.id,
            org_id=org_id,
            actor_id="actor",
            start_utc=start,
            end_utc=end,
            timezone_name="UTC",
        )
        assert len(provider.imports) == 2
        assert provider.imports[0][1] != provider.imports[1][1]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_replayed_source_uses_existing_membership_and_revision_failure_recovers() -> None:
    org_id = "org"
    provider = _Provider((_record("record-1"),))
    collections = _Collections("collection-a", org_id)
    service, _, engine = await _service(provider, collections)
    revisions = cast(_Revisions, service._revision_publisher)
    try:
        _, _, rule_id = await _configured_rule(
            service, collection_id="collection-a", org_id=org_id
        )
        start = datetime(2026, 8, 15, 0, tzinfo=UTC)
        end = start + timedelta(hours=2)
        revisions.fail = True
        first = await service.run_backfill(
            collection_id="collection-a",
            rule_id=rule_id,
            org_id=org_id,
            actor_id="actor",
            start_utc=start,
            end_utc=end,
            timezone_name="UTC",
        )
        assert first.run.status == "needs_attention"
        assert first.run.collection_revision_id is None
        assert collections.link_calls == 1

        revisions.fail = False
        publication_retry = await service.retry_failed(
            run_id=first.run.id, org_id=org_id, actor_id="actor"
        )
        assert publication_retry.run.status == "completed"
        assert publication_retry.run.collection_revision_id is not None
        assert collections.link_calls == 1
        assert len(provider.imports) == 1

        replayed = await service.run_backfill(
            collection_id="collection-a",
            rule_id=rule_id,
            org_id=org_id,
            actor_id="actor",
            start_utc=start,
            end_utc=end,
            timezone_name="UTC",
        )
        assert replayed.run.status == "completed"
        assert replayed.run.stats["skipped"] == 1
        assert collections.link_calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rule_dependencies_and_backfill_range_are_explicitly_scoped() -> None:
    org_id = "org"
    provider = _Provider((_record("record-1"),))
    collections = _Collections("collection-a", org_id)
    service, _, engine = await _service(provider, collections)
    try:
        first = await service.create_connector(
            org_id=org_id,
            actor_id="actor",
            provider_id="test",
            name="first",
            config={},
        )
        profile = await service.create_import_profile(
            org_id=org_id,
            actor_id="actor",
            connector_id=first.id,
            name="first profile",
            settings={},
        )
        second = await service.create_connector(
            org_id=org_id,
            actor_id="actor",
            provider_id="test",
            name="second",
            config={},
        )
        condition = FilterGroup(
            FilterCombinator.ALL,
            (FilterPredicate("layer", FilterOperator.EQ, "M1"),),
        )
        with pytest.raises(
            SourceDiscoveryValidationError, match="does not belong"
        ):
            await service.create_rule(
                collection_id="collection-a",
                org_id=org_id,
                actor_id="actor",
                name="invalid pairing",
                connector_id=second.id,
                import_profile_version_id=profile.id,
                condition=condition,
            )

        rule, _ = await service.create_rule(
            collection_id="collection-a",
            org_id=org_id,
            actor_id="actor",
            name="valid",
            connector_id=first.id,
            import_profile_version_id=profile.id,
            condition=condition,
        )
        with pytest.raises(SourceDiscoveryValidationError, match="explicit UTC"):
            await service.preview_backfill(
                collection_id="collection-a",
                rule_id=rule.id,
                org_id=org_id,
                start_utc=datetime.fromisoformat("2026-08-15T08:00:00+08:00"),
                end_utc=datetime.fromisoformat("2026-08-15T09:00:00+08:00"),
                timezone_name="Asia/Shanghai",
                representative_limit=3,
            )
        instant = datetime(2026, 8, 15, tzinfo=UTC)
        with pytest.raises(SourceDiscoveryValidationError, match="start_utc < end_utc"):
            await service.preview_backfill(
                collection_id="collection-a",
                rule_id=rule.id,
                org_id=org_id,
                start_utc=instant,
                end_utc=instant,
                timezone_name="UTC",
                representative_limit=3,
            )
    finally:
        await engine.dispose()
