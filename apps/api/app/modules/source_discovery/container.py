from __future__ import annotations

from injector import Module, provider, singleton

from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.sc.port.local import ScImportPort
from app.modules.source_discovery.adapter.sc_provider import ScSourceRecordProvider
from app.modules.source_discovery.adapter.sql_repository import (
    SourceDiscoverySqlRepository,
)
from app.modules.source_discovery.app.services.source_discovery_service import (
    SourceDiscoveryService,
)
from app.modules.source_discovery.domain.provider import SourceProviderCatalog
from app.modules.source_discovery.domain.repository import SourceDiscoveryRepository
from app.modules.source_discovery.port.local import SourceDiscoveryManagementPort
from app.shared.db.session import AppDatabaseSessionFactory


class SourceDiscoveryModule(Module):
    @provider
    @singleton
    def provide_repository_impl(
        self, session_factory: AppDatabaseSessionFactory
    ) -> SourceDiscoverySqlRepository:
        return SourceDiscoverySqlRepository(session_factory.sessionmaker)

    @provider
    @singleton
    def provide_repository(
        self, repository: SourceDiscoverySqlRepository
    ) -> SourceDiscoveryRepository:
        return repository

    @provider
    @singleton
    def provide_provider_catalog(
        self, upstream: ScUpstreamReader, importer: ScImportPort
    ) -> SourceProviderCatalog:
        return SourceProviderCatalog((ScSourceRecordProvider(upstream, importer),))

    @provider
    @singleton
    def provide_management_port(
        self, service: SourceDiscoveryService
    ) -> SourceDiscoveryManagementPort:
        return service
