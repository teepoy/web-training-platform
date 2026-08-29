from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.source_discovery.domain.conditions import (
    condition_from_json,
    condition_to_json,
)
from app.modules.source_discovery.domain.models import (
    DiscoveryRun,
    DiscoveryRunItem,
    FilterGroup,
    ImportProfileVersion,
    ImportReceipt,
    MembershipRule,
    MembershipRuleVersion,
    MembershipSuppression,
    ScAutomationPartition,
    SourceConnector,
    SourceMembership,
)
from app.modules.source_discovery.domain.errors import (
    ActiveDiscoveryRunExistsError,
    SourceDiscoveryConflictError,
)
from app.shared.db.models.source_discovery import (
    CollectionDiscoveryReceiptORM,
    CollectionDiscoveryRunItemORM,
    CollectionDiscoveryRunORM,
    CollectionImportReceiptORM,
    CollectionMembershipRuleORM,
    CollectionMembershipRuleVersionORM,
    CollectionMembershipSuppressionORM,
    CollectionSourceMembershipORM,
    ScAutomationPartitionORM,
    SourceConnectorORM,
    SourceImportProfileVersionORM,
)


def _db_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _connector(row: SourceConnectorORM) -> SourceConnector:
    return SourceConnector(
        id=row.id,
        org_id=row.org_id,
        provider_id=row.provider_id,
        name=row.name,
        config=cast(dict[str, object], row.config),
        enabled=row.enabled,
        created_by=row.created_by,
        created_at=_db_utc(row.created_at),
        updated_at=_db_utc(row.updated_at),
    )


def _profile(row: SourceImportProfileVersionORM) -> ImportProfileVersion:
    return ImportProfileVersion(
        id=row.id,
        profile_key=row.profile_key,
        version=row.version,
        org_id=row.org_id,
        connector_id=row.connector_id,
        name=row.name,
        settings=cast(dict[str, object], row.settings),
        max_records_per_run=row.max_records_per_run,
        max_rows_per_dataset=row.max_rows_per_dataset,
        created_by=row.created_by,
        created_at=_db_utc(row.created_at),
    )


def _rule(row: CollectionMembershipRuleORM) -> MembershipRule:
    return MembershipRule(
        id=row.id,
        org_id=row.org_id,
        collection_id=row.collection_id,
        name=row.name,
        status=row.status,
        active_version_id=row.active_version_id,
        activated_at=_db_utc(row.activated_at),
        live_cursor=cast(dict[str, object] | None, row.live_cursor),
        created_by=row.created_by,
        created_at=_db_utc(row.created_at),
        updated_at=_db_utc(row.updated_at),
    )


def _rule_version(row: CollectionMembershipRuleVersionORM) -> MembershipRuleVersion:
    condition = condition_from_json(cast(dict[str, object], row.condition))
    if not isinstance(condition, FilterGroup):
        raise ValueError("Stored membership rule root must be a group")
    return MembershipRuleVersion(
        id=row.id,
        rule_id=row.rule_id,
        version=row.version,
        connector_id=row.connector_id,
        import_profile_version_id=row.import_profile_version_id,
        condition=condition,
        created_by=row.created_by,
        created_at=_db_utc(row.created_at),
    )


def _partition(row: ScAutomationPartitionORM) -> ScAutomationPartition:
    return ScAutomationPartition(
        id=row.id,
        org_id=row.org_id,
        collection_id=row.collection_id,
        rule_id=row.rule_id,
        connector_id=row.connector_id,
        layer_id=row.layer_id,
        dimension=row.dimension,
        dimension_value=row.dimension_value,
        partition_key=row.partition_key,
        created_by=row.created_by,
        created_at=_db_utc(row.created_at),
    )


def _run(row: CollectionDiscoveryRunORM) -> DiscoveryRun:
    return DiscoveryRun(
        id=row.id,
        org_id=row.org_id,
        collection_id=row.collection_id,
        rule_id=row.rule_id,
        rule_version_id=row.rule_version_id,
        kind=row.kind,
        status=row.status,
        as_of_utc=_db_utc(row.as_of_utc),
        range_start_utc=(
            _db_utc(row.range_start_utc) if row.range_start_utc is not None else None
        ),
        range_end_utc=(
            _db_utc(row.range_end_utc) if row.range_end_utc is not None else None
        ),
        timezone_name=row.timezone_name,
        parent_run_id=row.parent_run_id,
        snapshot_revision_id=row.snapshot_revision_id,
        stats={
            str(key): int(value)
            for key, value in cast(dict[str, int], row.stats).items()
        },
        error_detail=row.error_detail,
        created_by=row.created_by,
        created_at=_db_utc(row.created_at),
        completed_at=(
            _db_utc(row.completed_at) if row.completed_at is not None else None
        ),
    )


def _run_item(row: CollectionDiscoveryRunItemORM) -> DiscoveryRunItem:
    return DiscoveryRunItem(
        id=row.id,
        run_id=row.run_id,
        connector_id=row.connector_id,
        source_record_key=row.source_record_key,
        source_version=row.source_version,
        observed_at=_db_utc(row.observed_at),
        source_payload=cast(dict[str, object], row.source_payload),
        status=row.status,
        dataset_id=row.dataset_id,
        member_id=row.member_id,
        error_detail=row.error_detail,
        created_at=_db_utc(row.created_at),
        updated_at=_db_utc(row.updated_at),
    )


def _import_receipt(row: CollectionImportReceiptORM) -> ImportReceipt:
    return ImportReceipt(
        id=row.id,
        collection_id=row.collection_id,
        connector_id=row.connector_id,
        source_record_key=row.source_record_key,
        source_version=row.source_version_key or None,
        import_profile_version_id=row.import_profile_version_id,
        status=row.status,
        dataset_id=row.dataset_id,
        attempts=row.attempts,
        last_error=row.last_error,
    )


def _source_membership(row: CollectionSourceMembershipORM) -> SourceMembership:
    return SourceMembership(
        id=row.id,
        collection_id=row.collection_id,
        connector_id=row.connector_id,
        source_record_key=row.source_record_key,
        source_version=row.source_version,
        dataset_id=row.dataset_id,
        member_id=row.member_id,
        admitted_by_rule_id=row.admitted_by_rule_id,
        admitted_by_run_id=row.admitted_by_run_id,
        created_at=_db_utc(row.created_at),
    )


def _suppression(row: CollectionMembershipSuppressionORM) -> MembershipSuppression:
    return MembershipSuppression(
        id=row.id,
        collection_id=row.collection_id,
        connector_id=row.connector_id,
        source_record_key=row.source_record_key,
        reason=row.reason,
        created_by=row.created_by,
        created_at=_db_utc(row.created_at),
        cleared_by=row.cleared_by,
        cleared_at=(_db_utc(row.cleared_at) if row.cleared_at is not None else None),
    )


class SourceDiscoverySqlRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_connector(self, connector: SourceConnector) -> SourceConnector:
        async with self._session_factory() as session:
            row = SourceConnectorORM(**asdict(connector))
            session.add(row)
            await session.commit()
            return _connector(row)

    async def list_connectors(self, org_id: str) -> list[SourceConnector]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(SourceConnectorORM)
                    .where(SourceConnectorORM.org_id == org_id)
                    .order_by(SourceConnectorORM.name, SourceConnectorORM.id)
                )
            ).scalars()
            return [_connector(row) for row in rows]

    async def get_connector(
        self, connector_id: str, org_id: str
    ) -> SourceConnector | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(SourceConnectorORM)
                .where(SourceConnectorORM.id == connector_id)
                .where(SourceConnectorORM.org_id == org_id)
            )
            return _connector(row) if row is not None else None

    async def create_profile_version(
        self, profile: ImportProfileVersion
    ) -> ImportProfileVersion:
        async with self._session_factory() as session:
            row = SourceImportProfileVersionORM(**asdict(profile))
            session.add(row)
            await session.commit()
            return _profile(row)

    async def list_profile_versions(
        self, connector_id: str, org_id: str
    ) -> list[ImportProfileVersion]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(SourceImportProfileVersionORM)
                    .where(SourceImportProfileVersionORM.connector_id == connector_id)
                    .where(SourceImportProfileVersionORM.org_id == org_id)
                    .order_by(
                        SourceImportProfileVersionORM.profile_key,
                        SourceImportProfileVersionORM.version.desc(),
                    )
                )
            ).scalars()
            return [_profile(row) for row in rows]

    async def get_profile_version(
        self, profile_version_id: str, org_id: str
    ) -> ImportProfileVersion | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(SourceImportProfileVersionORM)
                .where(SourceImportProfileVersionORM.id == profile_version_id)
                .where(SourceImportProfileVersionORM.org_id == org_id)
            )
            return _profile(row) if row is not None else None

    async def next_profile_version(self, profile_key: str, org_id: str) -> int:
        async with self._session_factory() as session:
            current = await session.scalar(
                select(func.max(SourceImportProfileVersionORM.version))
                .where(SourceImportProfileVersionORM.profile_key == profile_key)
                .where(SourceImportProfileVersionORM.org_id == org_id)
            )
            return int(current or 0) + 1

    async def create_rule(
        self, rule: MembershipRule, version: MembershipRuleVersion
    ) -> tuple[MembershipRule, MembershipRuleVersion]:
        async with self._session_factory() as session:
            rule_row = CollectionMembershipRuleORM(**asdict(rule))
            version_row = CollectionMembershipRuleVersionORM(
                id=version.id,
                rule_id=version.rule_id,
                version=version.version,
                connector_id=version.connector_id,
                import_profile_version_id=version.import_profile_version_id,
                condition=condition_to_json(version.condition),
                created_by=version.created_by,
                created_at=version.created_at,
            )
            session.add_all([rule_row, version_row])
            await session.commit()
            return _rule(rule_row), _rule_version(version_row)

    async def create_partition_rule(
        self,
        rule: MembershipRule,
        version: MembershipRuleVersion,
        partition: ScAutomationPartition,
    ) -> tuple[MembershipRule, MembershipRuleVersion, ScAutomationPartition]:
        async with self._session_factory() as session:
            rule_row = CollectionMembershipRuleORM(**asdict(rule))
            version_row = CollectionMembershipRuleVersionORM(
                id=version.id,
                rule_id=version.rule_id,
                version=version.version,
                connector_id=version.connector_id,
                import_profile_version_id=version.import_profile_version_id,
                condition=condition_to_json(version.condition),
                created_by=version.created_by,
                created_at=version.created_at,
            )
            partition_row = ScAutomationPartitionORM(**asdict(partition))
            session.add_all([rule_row, version_row, partition_row])
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise SourceDiscoveryConflictError(
                    "partition_assigned",
                    "This SC automation partition was assigned concurrently",
                ) from exc
            return (
                _rule(rule_row),
                _rule_version(version_row),
                _partition(partition_row),
            )

    async def list_partitions(
        self, collection_id: str, org_id: str
    ) -> list[ScAutomationPartition]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(ScAutomationPartitionORM)
                    .where(ScAutomationPartitionORM.collection_id == collection_id)
                    .where(ScAutomationPartitionORM.org_id == org_id)
                    .order_by(ScAutomationPartitionORM.created_at)
                )
            ).all()
            return [_partition(row) for row in rows]

    async def find_partition(
        self, org_id: str, connector_id: str, partition_key: str
    ) -> ScAutomationPartition | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ScAutomationPartitionORM)
                .where(ScAutomationPartitionORM.org_id == org_id)
                .where(ScAutomationPartitionORM.connector_id == connector_id)
                .where(ScAutomationPartitionORM.partition_key == partition_key)
            )
            return _partition(row) if row is not None else None

    async def get_partition_for_rule(
        self, rule_id: str, org_id: str
    ) -> ScAutomationPartition | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ScAutomationPartitionORM)
                .where(ScAutomationPartitionORM.rule_id == rule_id)
                .where(ScAutomationPartitionORM.org_id == org_id)
            )
            return _partition(row) if row is not None else None

    async def create_rule_version(
        self,
        version: MembershipRuleVersion,
        *,
        org_id: str,
        activated_at: datetime,
    ) -> tuple[MembershipRule, MembershipRuleVersion]:
        async with self._session_factory() as session:
            rule_row = await session.scalar(
                select(CollectionMembershipRuleORM)
                .where(CollectionMembershipRuleORM.id == version.rule_id)
                .where(CollectionMembershipRuleORM.org_id == org_id)
                .with_for_update()
            )
            if rule_row is None:
                raise LookupError("Membership rule not found")
            row = CollectionMembershipRuleVersionORM(
                id=version.id,
                rule_id=version.rule_id,
                version=version.version,
                connector_id=version.connector_id,
                import_profile_version_id=version.import_profile_version_id,
                condition=condition_to_json(version.condition),
                created_by=version.created_by,
                created_at=version.created_at,
            )
            session.add(row)
            rule_row.active_version_id = version.id
            rule_row.activated_at = activated_at
            rule_row.live_cursor = None
            rule_row.updated_at = activated_at
            await session.commit()
            return _rule(rule_row), _rule_version(row)

    async def list_rules(
        self, collection_id: str, org_id: str
    ) -> list[tuple[MembershipRule, MembershipRuleVersion]]:
        async with self._session_factory() as session:
            pairs = (
                await session.execute(
                    select(
                        CollectionMembershipRuleORM,
                        CollectionMembershipRuleVersionORM,
                    )
                    .join(
                        CollectionMembershipRuleVersionORM,
                        CollectionMembershipRuleVersionORM.id
                        == CollectionMembershipRuleORM.active_version_id,
                    )
                    .where(CollectionMembershipRuleORM.collection_id == collection_id)
                    .where(CollectionMembershipRuleORM.org_id == org_id)
                    .order_by(CollectionMembershipRuleORM.created_at)
                )
            ).all()
            return [(_rule(rule), _rule_version(version)) for rule, version in pairs]

    async def list_active_rules(self) -> list[MembershipRule]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(CollectionMembershipRuleORM)
                    .where(CollectionMembershipRuleORM.status == "active")
                    .order_by(
                        CollectionMembershipRuleORM.org_id,
                        CollectionMembershipRuleORM.collection_id,
                        CollectionMembershipRuleORM.created_at,
                    )
                )
            ).all()
            return [_rule(row) for row in rows]

    async def get_rule(
        self, rule_id: str, collection_id: str, org_id: str
    ) -> MembershipRule | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionMembershipRuleORM)
                .where(CollectionMembershipRuleORM.id == rule_id)
                .where(CollectionMembershipRuleORM.collection_id == collection_id)
                .where(CollectionMembershipRuleORM.org_id == org_id)
            )
            return _rule(row) if row is not None else None

    async def get_rule_version(
        self, version_id: str, rule_id: str
    ) -> MembershipRuleVersion | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionMembershipRuleVersionORM)
                .where(CollectionMembershipRuleVersionORM.id == version_id)
                .where(CollectionMembershipRuleVersionORM.rule_id == rule_id)
            )
            return _rule_version(row) if row is not None else None

    async def next_rule_version(self, rule_id: str) -> int:
        async with self._session_factory() as session:
            current = await session.scalar(
                select(func.max(CollectionMembershipRuleVersionORM.version)).where(
                    CollectionMembershipRuleVersionORM.rule_id == rule_id
                )
            )
            return int(current or 0) + 1

    async def update_live_cursor(
        self,
        rule_id: str,
        *,
        org_id: str,
        cursor: dict[str, object],
    ) -> None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionMembershipRuleORM)
                .where(CollectionMembershipRuleORM.id == rule_id)
                .where(CollectionMembershipRuleORM.org_id == org_id)
                .with_for_update()
            )
            if row is None:
                raise LookupError("Membership rule not found")
            row.live_cursor = cursor
            await session.commit()

    async def create_run(self, run: DiscoveryRun) -> DiscoveryRun:
        try:
            async with self._session_factory() as session:
                row = CollectionDiscoveryRunORM(**asdict(run))
                session.add(row)
                await session.commit()
                return _run(row)
        except IntegrityError as exc:
            active = await self.get_active_run(run.rule_id)
            if active is None:
                raise
            raise ActiveDiscoveryRunExistsError(active.id) from exc

    async def get_active_run(self, rule_id: str) -> DiscoveryRun | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionDiscoveryRunORM)
                .where(CollectionDiscoveryRunORM.rule_id == rule_id)
                .where(CollectionDiscoveryRunORM.status == "running")
                .order_by(CollectionDiscoveryRunORM.created_at)
                .limit(1)
            )
            return _run(row) if row is not None else None

    async def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        stats: dict[str, int],
        snapshot_revision_id: str | None,
        error_detail: str | None,
        completed_at: datetime,
    ) -> DiscoveryRun:
        async with self._session_factory() as session:
            row = await session.get(CollectionDiscoveryRunORM, run_id)
            if row is None:
                raise LookupError("Discovery run not found")
            row.status = status
            row.stats = stats
            row.snapshot_revision_id = snapshot_revision_id
            row.error_detail = error_detail
            row.completed_at = completed_at
            await session.commit()
            return _run(row)

    async def get_run(self, run_id: str, org_id: str) -> DiscoveryRun | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionDiscoveryRunORM)
                .where(CollectionDiscoveryRunORM.id == run_id)
                .where(CollectionDiscoveryRunORM.org_id == org_id)
            )
            return _run(row) if row is not None else None

    async def create_run_item(self, item: DiscoveryRunItem) -> DiscoveryRunItem:
        async with self._session_factory() as session:
            row = CollectionDiscoveryRunItemORM(**asdict(item))
            session.add(row)
            await session.commit()
            return _run_item(row)

    async def update_run_item(
        self,
        item_id: str,
        *,
        status: str,
        dataset_id: str | None,
        member_id: str | None,
        error_detail: str | None,
        updated_at: datetime,
    ) -> DiscoveryRunItem:
        async with self._session_factory() as session:
            row = await session.get(CollectionDiscoveryRunItemORM, item_id)
            if row is None:
                raise LookupError("Discovery run item not found")
            row.status = status
            row.dataset_id = dataset_id
            row.member_id = member_id
            row.error_detail = error_detail
            row.updated_at = updated_at
            await session.commit()
            return _run_item(row)

    async def list_run_items(self, run_id: str) -> list[DiscoveryRunItem]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(CollectionDiscoveryRunItemORM)
                    .where(CollectionDiscoveryRunItemORM.run_id == run_id)
                    .order_by(CollectionDiscoveryRunItemORM.created_at)
                )
            ).scalars()
            return [_run_item(row) for row in rows]

    async def get_source_membership(
        self, collection_id: str, connector_id: str, source_record_key: str
    ) -> SourceMembership | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionSourceMembershipORM)
                .where(CollectionSourceMembershipORM.collection_id == collection_id)
                .where(CollectionSourceMembershipORM.connector_id == connector_id)
                .where(
                    CollectionSourceMembershipORM.source_record_key == source_record_key
                )
            )
            return _source_membership(row) if row is not None else None

    async def create_source_membership(
        self, membership: SourceMembership
    ) -> tuple[SourceMembership, bool]:
        async with self._session_factory() as session:
            row = CollectionSourceMembershipORM(**asdict(membership))
            session.add(row)
            try:
                await session.commit()
                return _source_membership(row), True
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(CollectionSourceMembershipORM)
                    .where(
                        CollectionSourceMembershipORM.collection_id
                        == membership.collection_id
                    )
                    .where(
                        CollectionSourceMembershipORM.connector_id
                        == membership.connector_id
                    )
                    .where(
                        CollectionSourceMembershipORM.source_record_key
                        == membership.source_record_key
                    )
                )
                if existing is None:
                    raise
                return _source_membership(existing), False

    async def reserve_import(
        self,
        *,
        receipt: ImportReceipt,
        org_id: str,
        retry_failed: bool,
        updated_at: datetime,
    ) -> tuple[ImportReceipt, bool]:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionImportReceiptORM)
                .where(
                    CollectionImportReceiptORM.collection_id == receipt.collection_id
                )
                .where(CollectionImportReceiptORM.connector_id == receipt.connector_id)
                .where(
                    CollectionImportReceiptORM.source_record_key
                    == receipt.source_record_key
                )
                .where(
                    CollectionImportReceiptORM.source_version_key
                    == (receipt.source_version or "")
                )
                .where(
                    CollectionImportReceiptORM.import_profile_version_id
                    == receipt.import_profile_version_id
                )
                .with_for_update()
            )
            if row is not None:
                if row.status == "failed" and retry_failed:
                    row.status = "staging"
                    row.attempts += 1
                    row.last_error = None
                    row.updated_at = updated_at
                    await session.commit()
                    return _import_receipt(row), True
                return _import_receipt(row), False

            row = CollectionImportReceiptORM(
                id=receipt.id,
                org_id=org_id,
                collection_id=receipt.collection_id,
                connector_id=receipt.connector_id,
                source_record_key=receipt.source_record_key,
                source_version_key=receipt.source_version or "",
                import_profile_version_id=receipt.import_profile_version_id,
                status=receipt.status,
                dataset_id=receipt.dataset_id,
                attempts=receipt.attempts,
                last_error=receipt.last_error,
                created_at=updated_at,
                updated_at=updated_at,
            )
            session.add(row)
            try:
                await session.commit()
                return _import_receipt(row), True
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(CollectionImportReceiptORM)
                    .where(
                        CollectionImportReceiptORM.collection_id
                        == receipt.collection_id
                    )
                    .where(
                        CollectionImportReceiptORM.connector_id == receipt.connector_id
                    )
                    .where(
                        CollectionImportReceiptORM.source_record_key
                        == receipt.source_record_key
                    )
                    .where(
                        CollectionImportReceiptORM.source_version_key
                        == (receipt.source_version or "")
                    )
                    .where(
                        CollectionImportReceiptORM.import_profile_version_id
                        == receipt.import_profile_version_id
                    )
                )
                if existing is None:
                    raise
                return _import_receipt(existing), False

    async def finish_import(
        self,
        receipt_id: str,
        *,
        status: str,
        dataset_id: str | None,
        last_error: str | None,
        updated_at: datetime,
    ) -> ImportReceipt:
        async with self._session_factory() as session:
            row = await session.get(CollectionImportReceiptORM, receipt_id)
            if row is None:
                raise LookupError("Import receipt not found")
            row.status = status
            row.dataset_id = dataset_id
            row.last_error = last_error
            row.updated_at = updated_at
            await session.commit()
            return _import_receipt(row)

    async def get_discovery_receipt(
        self,
        *,
        rule_id: str,
        connector_id: str,
        source_record_key: str,
        source_version: str | None,
        import_profile_version_id: str,
    ) -> tuple[str, str | None, str | None] | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionDiscoveryReceiptORM)
                .where(CollectionDiscoveryReceiptORM.rule_id == rule_id)
                .where(CollectionDiscoveryReceiptORM.connector_id == connector_id)
                .where(
                    CollectionDiscoveryReceiptORM.source_record_key == source_record_key
                )
                .where(
                    CollectionDiscoveryReceiptORM.source_version_key
                    == (source_version or "")
                )
                .where(
                    CollectionDiscoveryReceiptORM.import_profile_version_id
                    == import_profile_version_id
                )
            )
            if row is None:
                return None
            return row.status, row.dataset_id, row.member_id

    async def upsert_discovery_receipt(
        self,
        *,
        collection_id: str,
        rule_id: str,
        connector_id: str,
        source_record_key: str,
        source_version: str | None,
        import_profile_version_id: str,
        status: str,
        dataset_id: str | None,
        member_id: str | None,
        first_run_id: str,
        updated_at: datetime,
    ) -> None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionDiscoveryReceiptORM)
                .where(CollectionDiscoveryReceiptORM.rule_id == rule_id)
                .where(CollectionDiscoveryReceiptORM.connector_id == connector_id)
                .where(
                    CollectionDiscoveryReceiptORM.source_record_key == source_record_key
                )
                .where(
                    CollectionDiscoveryReceiptORM.source_version_key
                    == (source_version or "")
                )
                .where(
                    CollectionDiscoveryReceiptORM.import_profile_version_id
                    == import_profile_version_id
                )
                .with_for_update()
            )
            if row is None:
                row = CollectionDiscoveryReceiptORM(
                    id=str(uuid4()),
                    collection_id=collection_id,
                    rule_id=rule_id,
                    connector_id=connector_id,
                    source_record_key=source_record_key,
                    source_version_key=source_version or "",
                    import_profile_version_id=import_profile_version_id,
                    status=status,
                    dataset_id=dataset_id,
                    member_id=member_id,
                    first_run_id=first_run_id,
                    updated_at=updated_at,
                )
                session.add(row)
            else:
                row.status = status
                row.dataset_id = dataset_id
                row.member_id = member_id
                row.updated_at = updated_at
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(CollectionDiscoveryReceiptORM)
                    .where(CollectionDiscoveryReceiptORM.rule_id == rule_id)
                    .where(CollectionDiscoveryReceiptORM.connector_id == connector_id)
                    .where(
                        CollectionDiscoveryReceiptORM.source_record_key
                        == source_record_key
                    )
                    .where(
                        CollectionDiscoveryReceiptORM.source_version_key
                        == (source_version or "")
                    )
                    .where(
                        CollectionDiscoveryReceiptORM.import_profile_version_id
                        == import_profile_version_id
                    )
                    .with_for_update()
                )
                if existing is None:
                    raise
                existing.status = status
                existing.dataset_id = dataset_id
                existing.member_id = member_id
                existing.updated_at = updated_at
                await session.commit()

    async def get_active_suppression(
        self, collection_id: str, connector_id: str, source_record_key: str
    ) -> MembershipSuppression | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionMembershipSuppressionORM)
                .where(
                    CollectionMembershipSuppressionORM.collection_id == collection_id
                )
                .where(CollectionMembershipSuppressionORM.connector_id == connector_id)
                .where(
                    CollectionMembershipSuppressionORM.source_record_key
                    == source_record_key
                )
                .where(CollectionMembershipSuppressionORM.cleared_at.is_(None))
            )
            return _suppression(row) if row is not None else None

    async def create_suppression(
        self, suppression: MembershipSuppression
    ) -> MembershipSuppression:
        async with self._session_factory() as session:
            row = CollectionMembershipSuppressionORM(**asdict(suppression))
            session.add(row)
            await session.commit()
            return _suppression(row)

    async def clear_suppression(
        self,
        suppression_id: str,
        *,
        collection_id: str,
        actor_id: str,
        cleared_at: datetime,
    ) -> MembershipSuppression | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CollectionMembershipSuppressionORM)
                .where(CollectionMembershipSuppressionORM.id == suppression_id)
                .where(
                    CollectionMembershipSuppressionORM.collection_id == collection_id
                )
                .where(CollectionMembershipSuppressionORM.cleared_at.is_(None))
                .with_for_update()
            )
            if row is None:
                return None
            row.cleared_by = actor_id
            row.cleared_at = cleared_at
            await session.commit()
            return _suppression(row)
