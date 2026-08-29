from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.modules.source_discovery.domain.models import (
    CollectionDiscoveryPoll,
    DiscoveryExecution,
    FilterGroup,
    ImportProfileVersion,
    MembershipRule,
    MembershipRuleVersion,
    MembershipSuppression,
    SourceConnector,
    SourceEstimate,
    SourceProviderDescriptor,
)


class CollectionDiscoveryPollingPort(Protocol):
    async def poll_active_rules(
        self,
        *,
        as_of_utc: datetime,
        actor_id: str,
    ) -> CollectionDiscoveryPoll: ...


class SourceDiscoveryManagementPort(Protocol):
    def list_provider_descriptors(self) -> tuple[SourceProviderDescriptor, ...]: ...

    async def create_connector(
        self,
        *,
        org_id: str,
        actor_id: str,
        provider_id: str,
        name: str,
        config: dict[str, object],
    ) -> SourceConnector: ...

    async def list_connectors(self, org_id: str) -> list[SourceConnector]: ...

    async def list_import_profiles(
        self, connector_id: str, org_id: str
    ) -> list[ImportProfileVersion]: ...

    async def create_import_profile(
        self,
        *,
        org_id: str,
        actor_id: str,
        connector_id: str,
        name: str,
        settings: dict[str, object],
        max_records_per_run: int,
        max_rows_per_dataset: int,
    ) -> ImportProfileVersion: ...

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
    ) -> tuple[MembershipRule, MembershipRuleVersion]: ...

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
    ) -> tuple[MembershipRule, MembershipRuleVersion]: ...

    async def list_rules(
        self, collection_id: str, org_id: str
    ) -> list[tuple[MembershipRule, MembershipRuleVersion]]: ...

    async def run_live(
        self,
        *,
        collection_id: str,
        rule_id: str,
        org_id: str,
        actor_id: str,
        as_of_utc: datetime,
    ) -> DiscoveryExecution: ...

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
    ) -> SourceEstimate: ...

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
    ) -> DiscoveryExecution: ...

    async def retry_failed(
        self,
        *,
        run_id: str,
        org_id: str,
        actor_id: str,
    ) -> DiscoveryExecution: ...

    async def get_run(self, run_id: str, org_id: str) -> DiscoveryExecution: ...

    async def suppress_source_member(
        self,
        *,
        collection_id: str,
        connector_id: str,
        source_record_key: str,
        org_id: str,
        actor_id: str,
        expected_definition_version: int,
        reason: str,
    ) -> MembershipSuppression: ...

    async def clear_suppression(
        self,
        *,
        collection_id: str,
        suppression_id: str,
        org_id: str,
        actor_id: str,
    ) -> MembershipSuppression: ...
