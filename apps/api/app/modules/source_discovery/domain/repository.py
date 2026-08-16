from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.modules.source_discovery.domain.models import (
    DiscoveryRun,
    DiscoveryRunItem,
    ImportProfileVersion,
    ImportReceipt,
    MembershipRule,
    MembershipRuleVersion,
    MembershipSuppression,
    SourceConnector,
    SourceMembership,
)


class SourceDiscoveryRepository(Protocol):
    async def create_connector(self, connector: SourceConnector) -> SourceConnector: ...

    async def list_connectors(self, org_id: str) -> list[SourceConnector]: ...

    async def get_connector(
        self, connector_id: str, org_id: str
    ) -> SourceConnector | None: ...

    async def create_profile_version(
        self, profile: ImportProfileVersion
    ) -> ImportProfileVersion: ...

    async def list_profile_versions(
        self, connector_id: str, org_id: str
    ) -> list[ImportProfileVersion]: ...

    async def get_profile_version(
        self, profile_version_id: str, org_id: str
    ) -> ImportProfileVersion | None: ...

    async def next_profile_version(self, profile_key: str, org_id: str) -> int: ...

    async def create_rule(
        self, rule: MembershipRule, version: MembershipRuleVersion
    ) -> tuple[MembershipRule, MembershipRuleVersion]: ...

    async def create_rule_version(
        self,
        version: MembershipRuleVersion,
        *,
        org_id: str,
        activated_at: datetime,
    ) -> tuple[MembershipRule, MembershipRuleVersion]: ...

    async def list_rules(
        self, collection_id: str, org_id: str
    ) -> list[tuple[MembershipRule, MembershipRuleVersion]]: ...

    async def get_rule(
        self, rule_id: str, collection_id: str, org_id: str
    ) -> MembershipRule | None: ...

    async def get_rule_version(
        self, version_id: str, rule_id: str
    ) -> MembershipRuleVersion | None: ...

    async def next_rule_version(self, rule_id: str) -> int: ...

    async def update_live_cursor(
        self,
        rule_id: str,
        *,
        org_id: str,
        cursor: dict[str, object],
    ) -> None: ...

    async def create_run(self, run: DiscoveryRun) -> DiscoveryRun: ...

    async def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        stats: dict[str, int],
        snapshot_revision_id: str | None,
        error_detail: str | None,
        completed_at: datetime,
    ) -> DiscoveryRun: ...

    async def get_run(self, run_id: str, org_id: str) -> DiscoveryRun | None: ...

    async def create_run_item(self, item: DiscoveryRunItem) -> DiscoveryRunItem: ...

    async def update_run_item(
        self,
        item_id: str,
        *,
        status: str,
        dataset_id: str | None,
        member_id: str | None,
        error_detail: str | None,
        updated_at: datetime,
    ) -> DiscoveryRunItem: ...

    async def list_run_items(self, run_id: str) -> list[DiscoveryRunItem]: ...

    async def get_source_membership(
        self, collection_id: str, connector_id: str, source_record_key: str
    ) -> SourceMembership | None: ...

    async def create_source_membership(
        self, membership: SourceMembership
    ) -> tuple[SourceMembership, bool]: ...

    async def reserve_import(
        self,
        *,
        receipt: ImportReceipt,
        org_id: str,
        retry_failed: bool,
        updated_at: datetime,
    ) -> tuple[ImportReceipt, bool]: ...

    async def finish_import(
        self,
        receipt_id: str,
        *,
        status: str,
        dataset_id: str | None,
        last_error: str | None,
        updated_at: datetime,
    ) -> ImportReceipt: ...

    async def get_discovery_receipt(
        self,
        *,
        rule_id: str,
        connector_id: str,
        source_record_key: str,
        source_version: str | None,
        import_profile_version_id: str,
    ) -> tuple[str, str | None, str | None] | None: ...

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
    ) -> None: ...

    async def get_active_suppression(
        self, collection_id: str, connector_id: str, source_record_key: str
    ) -> MembershipSuppression | None: ...

    async def create_suppression(
        self, suppression: MembershipSuppression
    ) -> MembershipSuppression: ...

    async def clear_suppression(
        self,
        suppression_id: str,
        *,
        collection_id: str,
        actor_id: str,
        cleared_at: datetime,
    ) -> MembershipSuppression | None: ...
