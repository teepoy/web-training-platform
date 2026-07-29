from __future__ import annotations

from fastapi import Request

from app.core.settings.domain.repository import SettingsRepository
from app.shared.injection import resolve


def get_settings_repository(request: Request) -> SettingsRepository:
    return resolve(request, SettingsRepository)
