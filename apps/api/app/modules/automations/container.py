from __future__ import annotations

from injector import Module, provider, singleton

from app.modules.automations.adapter import AutomationOverviewSqlRepository
from app.modules.automations.app.services import AutomationOverviewService
from app.modules.automations.domain import AutomationOverviewRepository
from app.modules.automations.port.local import AutomationOverviewPort
from app.shared.db.session import AppDatabaseSessionFactory


class AutomationsModule(Module):
    @provider
    @singleton
    def provide_repository_impl(
        self, session_factory: AppDatabaseSessionFactory
    ) -> AutomationOverviewSqlRepository:
        return AutomationOverviewSqlRepository(session_factory.sessionmaker)

    @provider
    @singleton
    def provide_repository(
        self, repository: AutomationOverviewSqlRepository
    ) -> AutomationOverviewRepository:
        return repository

    @provider
    @singleton
    def provide_overview_port(
        self, service: AutomationOverviewService
    ) -> AutomationOverviewPort:
        return service
