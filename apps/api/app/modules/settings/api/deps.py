from __future__ import annotations

from fastapi import Request

from app.modules.settings.domain.repository import SettingsRepository


def get_settings_repository(request: Request) -> SettingsRepository:
    return request.app.state.container.settings_repository
