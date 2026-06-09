from __future__ import annotations

from dataclasses import dataclass

from app.shared.context import SharedInfra

from .adapter.repositories.repository import InMemorySettingsRepository


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
