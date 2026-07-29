from __future__ import annotations

from dataclasses import dataclass

from injector import Module, inject, provider, singleton

from app.shared.context import SharedInfra

from .adapter.repositories.repository import InMemorySettingsRepository
from .domain.repository import SettingsRepository


@dataclass
class SettingsContext:
    """Settings module context.

    Attributes:
        settings_repository: In-memory key-value store for platform settings.
    """

    settings_repository: InMemorySettingsRepository


def init_settings(shared: SharedInfra) -> SettingsContext:
    """Build the settings module context from shared infrastructure.

    Args:
        shared: Shared infrastructure (session_factory, config, etc.).

    Returns:
        A new SettingsContext instance.
    """
    return SettingsContext(settings_repository=InMemorySettingsRepository())


class SettingsModule(Module):
    @inject
    @provider
    @singleton
    def provide_settings_context(self) -> SettingsContext:
        return SettingsContext(settings_repository=InMemorySettingsRepository())

    @provider
    @singleton
    def provide_settings_repository(
        self, context: SettingsContext
    ) -> SettingsRepository:
        return context.settings_repository
