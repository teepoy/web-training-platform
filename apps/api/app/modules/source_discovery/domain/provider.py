from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.modules.source_discovery.domain.models import (
    FilterGroup,
    ImportProfileVersion,
    SourceConnector,
    SourceDiscoveryBatch,
    SourceEstimate,
    SourceImportResult,
    SourceProviderDescriptor,
    SourceRecord,
)


class SourceRecordProvider(Protocol):
    @property
    def descriptor(self) -> SourceProviderDescriptor: ...

    async def discover(
        self,
        *,
        connector: SourceConnector,
        condition: FilterGroup,
        start_utc: datetime,
        end_utc: datetime,
        max_records: int,
    ) -> SourceDiscoveryBatch: ...

    async def estimate(
        self,
        *,
        connector: SourceConnector,
        condition: FilterGroup,
        start_utc: datetime,
        end_utc: datetime,
        representative_limit: int,
        max_records: int,
    ) -> SourceEstimate: ...

    async def import_record(
        self,
        *,
        connector: SourceConnector,
        profile: ImportProfileVersion,
        record: SourceRecord,
        org_id: str,
        actor_id: str,
    ) -> SourceImportResult: ...


class SourceProviderCatalog:
    def __init__(self, providers: tuple[SourceRecordProvider, ...]) -> None:
        self._providers = {
            provider.descriptor.provider_id: provider for provider in providers
        }
        if len(self._providers) != len(providers):
            raise ValueError("Source provider ids must be unique")

    def list_descriptors(self) -> tuple[SourceProviderDescriptor, ...]:
        return tuple(
            provider.descriptor for _, provider in sorted(self._providers.items())
        )

    def get(self, provider_id: str) -> SourceRecordProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"Unknown source provider: {provider_id}") from exc
