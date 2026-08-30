from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from injector import inject

from app.modules.dataset_collections.domain.models import NewCollectionMember
from app.modules.dataset_collections.port.local import (
    CollectionAutomationAdmissionPort,
    CollectionRevisionPublishingPort,
)
from app.modules.source_discovery.domain.conditions import (
    ConditionValidationError,
    validate_condition,
)
from app.modules.source_discovery.domain.errors import (
    ActiveDiscoveryRunExistsError,
    SourceDiscoveryConflictError,
    SourceDiscoveryNotFoundError,
    SourceDiscoveryValidationError,
)
from app.modules.source_discovery.domain.models import (
    DiscoveryExecution,
    DiscoveryRun,
    DiscoveryRunItem,
    FilterCombinator,
    FilterGroup,
    FilterOperator,
    FilterPredicate,
    ImportProfileVersion,
    ImportReceipt,
    MembershipRule,
    MembershipRuleVersion,
    ScAutomationPartition,
    SourceConnector,
    SourceDiscoveryBatch,
    SourceEstimate,
    SourceMembership,
    SourceProviderDescriptor,
    SourceRecord,
)
from app.modules.source_discovery.domain.provider import SourceProviderCatalog
from app.modules.source_discovery.domain.repository import SourceDiscoveryRepository


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class _ProcessedRecords:
    execution: DiscoveryExecution
    checkpoint: dict[str, object] | None


class SourceDiscoveryService:
    @inject
    def __init__(
        self,
        repository: SourceDiscoveryRepository,
        providers: SourceProviderCatalog,
        collections: CollectionAutomationAdmissionPort,
        revision_publisher: CollectionRevisionPublishingPort,
    ) -> None:
        self._repository = repository
        self._providers = providers
        self._collections = collections
        self._revision_publisher = revision_publisher

    def list_provider_descriptors(self) -> tuple[SourceProviderDescriptor, ...]:
        return self._providers.list_descriptors()

    async def create_connector(
        self,
        *,
        org_id: str,
        actor_id: str,
        provider_id: str,
        name: str,
        config: dict[str, object],
    ) -> SourceConnector:
        try:
            self._providers.get(provider_id)
        except KeyError as exc:
            raise SourceDiscoveryValidationError(
                "unknown_source_provider", str(exc)
            ) from exc
        now = _utcnow()
        return await self._repository.create_connector(
            SourceConnector(
                id=str(uuid4()),
                org_id=org_id,
                provider_id=provider_id,
                name=name.strip(),
                config=config,
                enabled=True,
                created_by=actor_id,
                created_at=now,
                updated_at=now,
            )
        )

    async def list_connectors(self, org_id: str) -> list[SourceConnector]:
        return await self._repository.list_connectors(org_id)

    async def list_import_profiles(
        self, connector_id: str, org_id: str
    ) -> list[ImportProfileVersion]:
        await self._connector(connector_id, org_id)
        return await self._repository.list_profile_versions(connector_id, org_id)

    async def create_import_profile(
        self,
        *,
        org_id: str,
        actor_id: str,
        connector_id: str,
        name: str,
        settings: dict[str, object],
    ) -> ImportProfileVersion:
        connector = await self._connector(connector_id, org_id)
        if not connector.enabled:
            raise SourceDiscoveryConflictError(
                "connector_disabled", "Source connector is disabled"
            )
        now = _utcnow()
        profile_key = str(uuid4())
        return await self._repository.create_profile_version(
            ImportProfileVersion(
                id=str(uuid4()),
                profile_key=profile_key,
                version=1,
                org_id=org_id,
                connector_id=connector.id,
                name=name.strip(),
                settings=settings,
                created_by=actor_id,
                created_at=now,
            )
        )

    async def create_rule(
        self,
        *,
        collection_id: str,
        org_id: str,
        actor_id: str,
        name: str,
        connector_id: str,
        import_profile_version_id: str,
        condition: FilterGroup,
    ) -> tuple[MembershipRule, MembershipRuleVersion]:
        await self._collections.get_collection(collection_id, org_id)
        connector, profile = await self._rule_dependencies(
            connector_id, import_profile_version_id, org_id
        )
        self._validate_condition(condition, connector.provider_id)
        now = _utcnow()
        rule_id = str(uuid4())
        version_id = str(uuid4())
        rule = MembershipRule(
            id=rule_id,
            org_id=org_id,
            collection_id=collection_id,
            name=name.strip(),
            status="active",
            active_version_id=version_id,
            activated_at=now,
            live_cursor=None,
            created_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        version = MembershipRuleVersion(
            id=version_id,
            rule_id=rule_id,
            version=1,
            connector_id=connector.id,
            import_profile_version_id=profile.id,
            condition=condition,
            created_by=actor_id,
            created_at=now,
        )
        return await self._repository.create_rule(rule, version)

    async def create_sc_partition(
        self,
        *,
        collection_id: str,
        org_id: str,
        actor_id: str,
        name: str,
        connector_id: str,
        import_profile_version_id: str,
        layer_id: str,
        device: str,
    ) -> tuple[MembershipRule, MembershipRuleVersion, ScAutomationPartition]:
        await self._collections.get_collection(collection_id, org_id)
        connector, profile = await self._rule_dependencies(
            connector_id, import_profile_version_id, org_id
        )
        if connector.provider_id != "sc":
            raise SourceDiscoveryValidationError(
                "partition_provider_invalid",
                "SC automation partitions require an SC source connector",
            )
        normalized_layer = layer_id.strip()
        normalized_device = device.strip()
        if not normalized_layer or not normalized_device:
            raise SourceDiscoveryValidationError(
                "partition_value_required",
                "SC automation partition layer and device are required",
            )
        partition_key = json.dumps(
            [normalized_layer, normalized_device],
            ensure_ascii=False,
        )
        existing = await self._repository.find_partition(
            org_id, connector.id, partition_key
        )
        if existing is not None:
            raise SourceDiscoveryConflictError(
                "partition_assigned",
                "SC automation partition is already assigned to Collection "
                f"{existing.collection_id}",
            )
        now = _utcnow()
        rule_id = str(uuid4())
        version_id = str(uuid4())
        condition = FilterGroup(
            combinator=FilterCombinator.ALL,
            children=(
                FilterPredicate(
                    field="layer_id",
                    operator=FilterOperator.EQ,
                    value=normalized_layer,
                ),
                FilterPredicate(
                    field="device",
                    operator=FilterOperator.EQ,
                    value=normalized_device,
                ),
            ),
        )
        rule = MembershipRule(
            id=rule_id,
            org_id=org_id,
            collection_id=collection_id,
            name=name.strip(),
            status="active",
            active_version_id=version_id,
            activated_at=now,
            live_cursor=None,
            created_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        version = MembershipRuleVersion(
            id=version_id,
            rule_id=rule_id,
            version=1,
            connector_id=connector.id,
            import_profile_version_id=profile.id,
            condition=condition,
            created_by=actor_id,
            created_at=now,
        )
        partition = ScAutomationPartition(
            id=str(uuid4()),
            org_id=org_id,
            collection_id=collection_id,
            rule_id=rule_id,
            connector_id=connector.id,
            layer_id=normalized_layer,
            device=normalized_device,
            partition_key=partition_key,
            created_by=actor_id,
            created_at=now,
        )
        return await self._repository.create_partition_rule(rule, version, partition)

    async def list_sc_partitions(
        self, collection_id: str, org_id: str
    ) -> list[ScAutomationPartition]:
        await self._collections.get_collection(collection_id, org_id)
        return await self._repository.list_partitions(collection_id, org_id)

    async def create_rule_version(
        self,
        *,
        collection_id: str,
        rule_id: str,
        org_id: str,
        actor_id: str,
        connector_id: str,
        import_profile_version_id: str,
        condition: FilterGroup,
    ) -> tuple[MembershipRule, MembershipRuleVersion]:
        rule = await self._rule(rule_id, collection_id, org_id)
        connector, profile = await self._rule_dependencies(
            connector_id, import_profile_version_id, org_id
        )
        self._validate_condition(condition, connector.provider_id)
        partition = await self._repository.get_partition_for_rule(rule.id, org_id)
        if partition is not None:
            expected_condition = self._sc_partition_condition(partition)
            if (
                connector.id != partition.connector_id
                or condition != expected_condition
            ):
                raise SourceDiscoveryConflictError(
                    "partition_rule_immutable",
                    "SC automation partition rules cannot change their source or "
                    "partition condition",
                )
        now = _utcnow()
        version = MembershipRuleVersion(
            id=str(uuid4()),
            rule_id=rule.id,
            version=await self._repository.next_rule_version(rule.id),
            connector_id=connector.id,
            import_profile_version_id=profile.id,
            condition=condition,
            created_by=actor_id,
            created_at=now,
        )
        return await self._repository.create_rule_version(
            version, org_id=org_id, activated_at=now
        )

    @staticmethod
    def _sc_partition_condition(partition: ScAutomationPartition) -> FilterGroup:
        return FilterGroup(
            combinator=FilterCombinator.ALL,
            children=(
                FilterPredicate(
                    field="layer_id",
                    operator=FilterOperator.EQ,
                    value=partition.layer_id,
                ),
                FilterPredicate(
                    field="device",
                    operator=FilterOperator.EQ,
                    value=partition.device,
                ),
            ),
        )

    async def list_rules(
        self, collection_id: str, org_id: str
    ) -> list[tuple[MembershipRule, MembershipRuleVersion]]:
        await self._collections.get_collection(collection_id, org_id)
        return await self._repository.list_rules(collection_id, org_id)

    async def run_live(
        self,
        *,
        collection_id: str,
        rule_id: str,
        org_id: str,
        actor_id: str,
        as_of_utc: datetime,
    ) -> DiscoveryExecution:
        as_of_utc = _require_utc(as_of_utc, "as_of_utc")
        rule, version, connector, profile = await self._execution_context(
            collection_id, rule_id, org_id
        )
        if rule.status != "active":
            raise SourceDiscoveryConflictError(
                "rule_not_active", "Membership rule is not active"
            )
        publication_start = _require_utc(rule.activated_at, "rule activation")
        if as_of_utc <= publication_start:
            raise SourceDiscoveryValidationError(
                "invalid_live_range", "as_of_utc must be after the live cursor"
            )
        try:
            run = await self._new_run(
                org_id=org_id,
                collection_id=collection_id,
                rule=rule,
                version=version,
                kind="live",
                actor_id=actor_id,
                as_of_utc=as_of_utc,
                start_utc=publication_start,
                end_utc=as_of_utc,
                timezone_name=None,
                parent_run_id=None,
            )
        except ActiveDiscoveryRunExistsError as exc:
            skipped = await self._repository.create_run(
                DiscoveryRun(
                    id=str(uuid4()),
                    org_id=org_id,
                    collection_id=collection_id,
                    rule_id=rule.id,
                    rule_version_id=version.id,
                    kind="live",
                    status="skipped",
                    as_of_utc=as_of_utc,
                    range_start_utc=publication_start,
                    range_end_utc=as_of_utc,
                    timezone_name=None,
                    parent_run_id=exc.run_id,
                    collection_revision_id=None,
                    stats={"skipped": 1},
                    error_detail=(
                        "Scheduled discovery skipped because the same membership "
                        f"rule still has active run {exc.run_id}"
                    ),
                    created_by=actor_id,
                    created_at=_utcnow(),
                    completed_at=_utcnow(),
                )
            )
            return DiscoveryExecution(run=skipped)
        try:
            batches = self._providers.get(connector.provider_id).discover_live(
                connector=connector,
                condition=version.condition,
                publication_start_utc=publication_start,
                publication_end_utc=as_of_utc,
                after_cursor=rule.live_cursor,
            )
            processed = await self._process_records(
                run=run,
                rule=rule,
                version=version,
                connector=connector,
                profile=profile,
                batches=batches,
                actor_id=actor_id,
                retry_failed=False,
            )
        except Exception as exc:
            execution = await self._fail_run(run, exc)
        else:
            execution = processed.execution
            if processed.checkpoint is not None:
                await self._repository.update_live_cursor(
                    rule.id,
                    org_id=org_id,
                    cursor=processed.checkpoint,
                )
        return execution

    async def preview_backfill(
        self,
        *,
        collection_id: str,
        rule_id: str,
        org_id: str,
        start_utc: datetime,
        end_utc: datetime,
        timezone_name: str,
        representative_limit: int,
    ) -> SourceEstimate:
        start_utc, end_utc = _backfill_range(start_utc, end_utc, timezone_name)
        _, version, connector, profile = await self._execution_context(
            collection_id, rule_id, org_id
        )
        provider = self._providers.get(connector.provider_id)
        if provider.descriptor.backfill_time_field is None:
            raise SourceDiscoveryValidationError(
                "backfill_not_supported", "Source provider does not support Backfill"
            )
        return await provider.estimate(
            connector=connector,
            condition=version.condition,
            start_utc=start_utc,
            end_utc=end_utc,
            representative_limit=representative_limit,
        )

    async def run_backfill(
        self,
        *,
        collection_id: str,
        rule_id: str,
        org_id: str,
        actor_id: str,
        start_utc: datetime,
        end_utc: datetime,
        timezone_name: str,
    ) -> DiscoveryExecution:
        start_utc, end_utc = _backfill_range(start_utc, end_utc, timezone_name)
        rule, version, connector, profile = await self._execution_context(
            collection_id, rule_id, org_id
        )
        provider = self._providers.get(connector.provider_id)
        if provider.descriptor.backfill_time_field is None:
            raise SourceDiscoveryValidationError(
                "backfill_not_supported", "Source provider does not support Backfill"
            )
        run = await self._new_run(
            org_id=org_id,
            collection_id=collection_id,
            rule=rule,
            version=version,
            kind="backfill",
            actor_id=actor_id,
            as_of_utc=_utcnow(),
            start_utc=start_utc,
            end_utc=end_utc,
            timezone_name=timezone_name,
            parent_run_id=None,
        )
        try:
            batches = provider.discover_backfill(
                connector=connector,
                condition=version.condition,
                start_utc=start_utc,
                end_utc=end_utc,
            )
            return (
                await self._process_records(
                    run=run,
                    rule=rule,
                    version=version,
                    connector=connector,
                    profile=profile,
                    batches=batches,
                    actor_id=actor_id,
                    retry_failed=False,
                )
            ).execution
        except Exception as exc:
            return await self._fail_run(run, exc)

    async def retry_failed(
        self,
        *,
        run_id: str,
        org_id: str,
        actor_id: str,
    ) -> DiscoveryExecution:
        parent = await self._repository.get_run(run_id, org_id)
        if parent is None:
            raise SourceDiscoveryNotFoundError(
                "run_not_found", "Discovery run not found"
            )
        failed = [
            item
            for item in await self._repository.list_run_items(parent.id)
            if item.status == "failed"
        ]
        if not failed:
            if (
                parent.status == "needs_attention"
                and parent.collection_revision_id is None
                and parent.stats.get("linked", 0) > 0
                and (parent.error_detail or "").startswith(
                    "Admissions succeeded but Revision publication failed"
                )
            ):
                return await self._retry_publication(parent, actor_id=actor_id)
            raise SourceDiscoveryConflictError(
                "no_failed_items", "Discovery run has no failed Source records"
            )
        rule = await self._rule(parent.rule_id, parent.collection_id, org_id)
        version = await self._repository.get_rule_version(
            parent.rule_version_id, parent.rule_id
        )
        if version is None:
            raise SourceDiscoveryNotFoundError(
                "rule_version_not_found", "Pinned membership rule version not found"
            )
        connector, profile = await self._rule_dependencies(
            version.connector_id, version.import_profile_version_id, org_id
        )
        retry_run = await self._new_run(
            org_id=org_id,
            collection_id=parent.collection_id,
            rule=rule,
            version=version,
            kind="retry",
            actor_id=actor_id,
            as_of_utc=_utcnow(),
            start_utc=parent.range_start_utc,
            end_utc=parent.range_end_utc,
            timezone_name=parent.timezone_name,
            parent_run_id=parent.id,
        )
        records = tuple(_record_from_payload(item.source_payload) for item in failed)
        return (
            await self._process_records(
                run=retry_run,
                rule=rule,
                version=version,
                connector=connector,
                profile=profile,
                batches=_single_batch(records),
                actor_id=actor_id,
                retry_failed=True,
            )
        ).execution

    async def get_run(self, run_id: str, org_id: str) -> DiscoveryExecution:
        run = await self._repository.get_run(run_id, org_id)
        if run is None:
            raise SourceDiscoveryNotFoundError(
                "run_not_found", "Discovery run not found"
            )
        return DiscoveryExecution(
            run=run,
            items=tuple(await self._repository.list_run_items(run.id)),
        )

    async def _process_records(
        self,
        *,
        run: DiscoveryRun,
        rule: MembershipRule,
        version: MembershipRuleVersion,
        connector: SourceConnector,
        profile: ImportProfileVersion,
        batches: AsyncIterator[SourceDiscoveryBatch],
        actor_id: str,
        retry_failed: bool,
    ) -> _ProcessedRecords:
        stats = {
            "scanned": 0,
            "matched": 0,
            "skipped": 0,
            "reused": 0,
            "imported": 0,
            "linked": 0,
            "succeeded": 0,
            "failed": 0,
        }
        checkpoint: dict[str, object] | None = None
        async for batch in batches:
            stats["scanned"] += len(batch.records)
            stats["matched"] += len(batch.records)
            for record in batch.records:
                item = await self._repository.create_run_item(
                    DiscoveryRunItem(
                        id=str(uuid4()),
                        run_id=run.id,
                        connector_id=connector.id,
                        source_record_key=record.record_key,
                        observed_at=record.observed_at,
                        source_payload=_record_payload(record),
                        status="pending",
                        dataset_id=None,
                        member_id=None,
                        error_detail=None,
                        created_at=_utcnow(),
                        updated_at=_utcnow(),
                    )
                )
                try:
                    item = await self._process_record(
                        item=item,
                        run=run,
                        rule=rule,
                        version=version,
                        connector=connector,
                        profile=profile,
                        record=record,
                        actor_id=actor_id,
                        retry_failed=retry_failed,
                    )
                except Exception as exc:
                    item = await self._update_item(
                        item,
                        "failed",
                        item.dataset_id,
                        item.member_id,
                        str(exc),
                    )
                if item.status == "replayed":
                    stats["skipped"] += 1
                elif item.status == "reused":
                    stats["reused"] += 1
                    stats["succeeded"] += 1
                elif item.status == "succeeded":
                    stats["imported"] += 1
                    stats["linked"] += 1
                    stats["succeeded"] += 1
                elif item.status == "failed":
                    stats["failed"] += 1
            if batch.checkpoint is not None:
                checkpoint = batch.checkpoint

        revision_id: str | None = None
        error_detail: str | None = None
        needs_attention = False
        if stats["linked"]:
            try:
                collection = await self._collections.get_collection(
                    run.collection_id, run.org_id
                )
                revision = (
                    await self._revision_publisher.create_revision_for_automation(
                        run.collection_id,
                        run.org_id,
                        actor_id=actor_id,
                        expected_definition_version=collection.definition_version,
                        trigger_kind=run.kind,
                        trigger_ref=run.id,
                    )
                )
                revision_id = revision.id
            except Exception as exc:
                needs_attention = True
                error_detail = (
                    f"Admissions succeeded but Revision publication failed: {exc}"
                )

        status = _run_status(stats, needs_attention=needs_attention)
        finished = await self._repository.finish_run(
            run.id,
            status=status,
            stats=stats,
            collection_revision_id=revision_id,
            error_detail=error_detail,
            completed_at=_utcnow(),
        )
        return _ProcessedRecords(
            execution=DiscoveryExecution(
                run=finished,
                items=tuple(await self._repository.list_run_items(run.id)),
            ),
            checkpoint=checkpoint,
        )

    async def _retry_publication(
        self, parent: DiscoveryRun, *, actor_id: str
    ) -> DiscoveryExecution:
        rule = await self._rule(parent.rule_id, parent.collection_id, parent.org_id)
        version = await self._repository.get_rule_version(
            parent.rule_version_id, parent.rule_id
        )
        if version is None:
            raise SourceDiscoveryNotFoundError(
                "rule_version_not_found", "Pinned membership rule version not found"
            )
        retry_run = await self._new_run(
            org_id=parent.org_id,
            collection_id=parent.collection_id,
            rule=rule,
            version=version,
            kind="retry",
            actor_id=actor_id,
            as_of_utc=_utcnow(),
            start_utc=parent.range_start_utc,
            end_utc=parent.range_end_utc,
            timezone_name=parent.timezone_name,
            parent_run_id=parent.id,
        )
        try:
            collection = await self._collections.get_collection(
                parent.collection_id, parent.org_id
            )
            revision = await self._revision_publisher.create_revision_for_automation(
                parent.collection_id,
                parent.org_id,
                actor_id=actor_id,
                expected_definition_version=collection.definition_version,
                trigger_kind="retry",
                trigger_ref=retry_run.id,
            )
        except Exception as exc:
            failed = await self._repository.finish_run(
                retry_run.id,
                status="needs_attention",
                stats=dict(parent.stats),
                collection_revision_id=None,
                error_detail=f"Revision publication Retry failed: {exc}",
                completed_at=_utcnow(),
            )
            return DiscoveryExecution(run=failed)
        completed = await self._repository.finish_run(
            retry_run.id,
            status="completed",
            stats=dict(parent.stats),
            collection_revision_id=revision.id,
            error_detail=None,
            completed_at=_utcnow(),
        )
        return DiscoveryExecution(run=completed)

    async def _process_record(
        self,
        *,
        item: DiscoveryRunItem,
        run: DiscoveryRun,
        rule: MembershipRule,
        version: MembershipRuleVersion,
        connector: SourceConnector,
        profile: ImportProfileVersion,
        record: SourceRecord,
        actor_id: str,
        retry_failed: bool,
    ) -> DiscoveryRunItem:
        receipt = await self._repository.get_discovery_receipt(
            rule_id=rule.id,
            connector_id=connector.id,
            source_record_key=record.record_key,
            import_profile_version_id=profile.id,
        )
        if receipt is not None and not (retry_failed and receipt[0] == "failed"):
            status, dataset_id, member_id = receipt
            if status in {"admitted", "reused"}:
                return await self._update_item(
                    item, "replayed", dataset_id, member_id, None
                )
            if status == "failed":
                return await self._update_item(
                    item,
                    "failed",
                    dataset_id,
                    member_id,
                    "Previous attempt failed; use failed-item Retry",
                )

        source = await self._repository.get_source_membership(
            run.collection_id, connector.id, record.record_key
        )
        if source is not None:
            await self._write_discovery_receipt(
                run,
                rule,
                profile,
                connector,
                record,
                "reused",
                source.dataset_id,
                source.member_id,
            )
            return await self._update_item(
                item, "reused", source.dataset_id, source.member_id, None
            )

        import_receipt, acquired = await self._repository.reserve_import(
            receipt=ImportReceipt(
                id=str(uuid4()),
                collection_id=run.collection_id,
                connector_id=connector.id,
                source_record_key=record.record_key,
                import_profile_version_id=profile.id,
                status="staging",
                dataset_id=None,
                attempts=1,
                last_error=None,
            ),
            org_id=run.org_id,
            retry_failed=retry_failed,
            updated_at=_utcnow(),
        )
        dataset_id = import_receipt.dataset_id
        if acquired:
            try:
                imported = await self._providers.get(
                    connector.provider_id
                ).import_record(
                    connector=connector,
                    profile=profile,
                    record=record,
                    org_id=run.org_id,
                    actor_id=actor_id,
                )
            except Exception as exc:
                detail = str(exc)
                await self._repository.finish_import(
                    import_receipt.id,
                    status="failed",
                    dataset_id=None,
                    last_error=detail,
                    updated_at=_utcnow(),
                )
                await self._write_discovery_receipt(
                    run, rule, profile, connector, record, "failed", None, None
                )
                return await self._update_item(item, "failed", None, None, detail)
            dataset_id = imported.dataset_id
            await self._repository.finish_import(
                import_receipt.id,
                status="ready",
                dataset_id=dataset_id,
                last_error=None,
                updated_at=_utcnow(),
            )
        elif import_receipt.status == "staging":
            return await self._update_item(
                item,
                "failed",
                None,
                None,
                "The same scoped import is already running",
            )
        elif import_receipt.status == "failed":
            return await self._update_item(
                item,
                "failed",
                None,
                None,
                import_receipt.last_error or "Previous scoped import failed",
            )
        if dataset_id is None:
            return await self._update_item(
                item, "failed", None, None, "Ready import receipt has no Dataset"
            )

        try:
            collection = await self._collections.get_collection(
                run.collection_id, run.org_id
            )
            members = await self._collections.list_members(
                run.collection_id, run.org_id
            )
            next_position = max((member.position for member in members), default=-1) + 1
            _, linked_members = await self._collections.admit_members_for_automation(
                run.collection_id,
                run.org_id,
                actor_id=actor_id,
                expected_definition_version=collection.definition_version,
                members=(
                    NewCollectionMember(
                        source_dataset_id=dataset_id,
                        position=next_position,
                    ),
                ),
            )
            member = next(
                member
                for member in linked_members
                if member.source_dataset_id == dataset_id
            )
            (
                source_membership,
                created,
            ) = await self._repository.create_source_membership(
                SourceMembership(
                    id=str(uuid4()),
                    collection_id=run.collection_id,
                    connector_id=connector.id,
                    source_record_key=record.record_key,
                    dataset_id=dataset_id,
                    member_id=member.id,
                    admitted_by_rule_id=rule.id,
                    admitted_by_run_id=run.id,
                    created_at=_utcnow(),
                )
            )
            if not created:
                member_id = source_membership.member_id
                dataset_id = source_membership.dataset_id
                result_status = "reused"
            else:
                member_id = member.id
                result_status = "admitted"
        except Exception as exc:
            detail = str(exc)
            await self._write_discovery_receipt(
                run, rule, profile, connector, record, "failed", dataset_id, None
            )
            return await self._update_item(item, "failed", dataset_id, None, detail)

        await self._write_discovery_receipt(
            run,
            rule,
            profile,
            connector,
            record,
            result_status,
            dataset_id,
            member_id,
        )
        return await self._update_item(
            item,
            "succeeded" if result_status == "admitted" else "reused",
            dataset_id,
            member_id,
            None,
        )

    async def _write_discovery_receipt(
        self,
        run: DiscoveryRun,
        rule: MembershipRule,
        profile: ImportProfileVersion,
        connector: SourceConnector,
        record: SourceRecord,
        status: str,
        dataset_id: str | None,
        member_id: str | None,
    ) -> None:
        await self._repository.upsert_discovery_receipt(
            collection_id=run.collection_id,
            rule_id=rule.id,
            connector_id=connector.id,
            source_record_key=record.record_key,
            import_profile_version_id=profile.id,
            status=status,
            dataset_id=dataset_id,
            member_id=member_id,
            first_run_id=run.id,
            updated_at=_utcnow(),
        )

    async def _update_item(
        self,
        item: DiscoveryRunItem,
        status: str,
        dataset_id: str | None,
        member_id: str | None,
        error_detail: str | None,
    ) -> DiscoveryRunItem:
        return await self._repository.update_run_item(
            item.id,
            status=status,
            dataset_id=dataset_id,
            member_id=member_id,
            error_detail=error_detail,
            updated_at=_utcnow(),
        )

    async def _execution_context(
        self, collection_id: str, rule_id: str, org_id: str
    ) -> tuple[
        MembershipRule,
        MembershipRuleVersion,
        SourceConnector,
        ImportProfileVersion,
    ]:
        rule = await self._rule(rule_id, collection_id, org_id)
        version = await self._repository.get_rule_version(
            rule.active_version_id, rule.id
        )
        if version is None:
            raise SourceDiscoveryNotFoundError(
                "rule_version_not_found", "Active membership rule version not found"
            )
        connector, profile = await self._rule_dependencies(
            version.connector_id, version.import_profile_version_id, org_id
        )
        return rule, version, connector, profile

    async def _rule_dependencies(
        self, connector_id: str, profile_version_id: str, org_id: str
    ) -> tuple[SourceConnector, ImportProfileVersion]:
        connector = await self._connector(connector_id, org_id)
        if not connector.enabled:
            raise SourceDiscoveryConflictError(
                "connector_disabled", "Source connector is disabled"
            )
        profile = await self._repository.get_profile_version(profile_version_id, org_id)
        if profile is None:
            raise SourceDiscoveryNotFoundError(
                "import_profile_not_found", "Import profile version not found"
            )
        if profile.connector_id != connector.id or profile.org_id != org_id:
            raise SourceDiscoveryValidationError(
                "profile_connector_mismatch",
                "Import profile version does not belong to this connector and organization",
            )
        return connector, profile

    async def _connector(self, connector_id: str, org_id: str) -> SourceConnector:
        connector = await self._repository.get_connector(connector_id, org_id)
        if connector is None:
            raise SourceDiscoveryNotFoundError(
                "connector_not_found", "Source connector not found"
            )
        return connector

    async def _rule(
        self, rule_id: str, collection_id: str, org_id: str
    ) -> MembershipRule:
        rule = await self._repository.get_rule(rule_id, collection_id, org_id)
        if rule is None:
            raise SourceDiscoveryNotFoundError(
                "rule_not_found", "Membership rule not found"
            )
        return rule

    def _validate_condition(self, condition: FilterGroup, provider_id: str) -> None:
        try:
            descriptor = self._providers.get(provider_id).descriptor
            validate_condition(condition, descriptor)
        except (KeyError, ConditionValidationError) as exc:
            raise SourceDiscoveryValidationError("invalid_condition", str(exc)) from exc

    async def _new_run(
        self,
        *,
        org_id: str,
        collection_id: str,
        rule: MembershipRule,
        version: MembershipRuleVersion,
        kind: str,
        actor_id: str,
        as_of_utc: datetime,
        start_utc: datetime | None,
        end_utc: datetime | None,
        timezone_name: str | None,
        parent_run_id: str | None,
    ) -> DiscoveryRun:
        now = _utcnow()
        return await self._repository.create_run(
            DiscoveryRun(
                id=str(uuid4()),
                org_id=org_id,
                collection_id=collection_id,
                rule_id=rule.id,
                rule_version_id=version.id,
                kind=kind,
                status="running",
                as_of_utc=as_of_utc,
                range_start_utc=start_utc,
                range_end_utc=end_utc,
                timezone_name=timezone_name,
                parent_run_id=parent_run_id,
                collection_revision_id=None,
                stats={},
                error_detail=None,
                created_by=actor_id,
                created_at=now,
                completed_at=None,
            )
        )

    async def _fail_run(self, run: DiscoveryRun, exc: Exception) -> DiscoveryExecution:
        failed = await self._repository.finish_run(
            run.id,
            status="failed",
            stats={"scanned": 0, "matched": 0, "succeeded": 0, "failed": 0},
            collection_revision_id=None,
            error_detail=str(exc),
            completed_at=_utcnow(),
        )
        return DiscoveryExecution(run=failed)


def _require_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SourceDiscoveryValidationError(
            "utc_required", f"{field_name} must be timezone-aware UTC"
        )
    offset = value.utcoffset()
    if offset is None:
        raise SourceDiscoveryValidationError(
            "utc_required", f"{field_name} must be timezone-aware UTC"
        )
    normalized = value.astimezone(UTC)
    if offset.total_seconds() != 0:
        raise SourceDiscoveryValidationError(
            "utc_required", f"{field_name} must use an explicit UTC offset"
        )
    return normalized


def _backfill_range(
    start_utc: datetime, end_utc: datetime, timezone_name: str
) -> tuple[datetime, datetime]:
    start = _require_utc(start_utc, "start_utc")
    end = _require_utc(end_utc, "end_utc")
    if start >= end:
        raise SourceDiscoveryValidationError(
            "invalid_backfill_range", "Backfill requires start_utc < end_utc"
        )
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise SourceDiscoveryValidationError(
            "invalid_timezone", "Backfill timezone must be a valid IANA name"
        ) from exc
    return start, end


def _record_payload(record: SourceRecord) -> dict[str, object]:
    return {
        "record_key": record.record_key,
        "observed_at": record.observed_at.isoformat(),
        "display_name": record.display_name,
        "attributes": record.attributes,
    }


def _record_from_payload(payload: dict[str, object]) -> SourceRecord:
    record_key = payload.get("record_key")
    observed_at = payload.get("observed_at")
    display_name = payload.get("display_name")
    attributes = payload.get("attributes")
    if (
        not isinstance(record_key, str)
        or not isinstance(observed_at, str)
        or not isinstance(display_name, str)
        or not isinstance(attributes, dict)
    ):
        raise SourceDiscoveryValidationError(
            "invalid_retry_payload", "Stored failed Source record is invalid"
        )
    return SourceRecord(
        record_key=record_key,
        observed_at=datetime.fromisoformat(observed_at),
        display_name=display_name,
        attributes=attributes,
    )


async def _single_batch(
    records: tuple[SourceRecord, ...],
) -> AsyncIterator[SourceDiscoveryBatch]:
    yield SourceDiscoveryBatch(records=records, checkpoint=None)


def _run_status(stats: dict[str, int], *, needs_attention: bool) -> str:
    if needs_attention:
        return "needs_attention"
    if stats["failed"] and stats["succeeded"]:
        return "partial"
    if stats["failed"]:
        return "failed"
    return "completed"
