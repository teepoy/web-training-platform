from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.modules.settings.port.http.deps import get_settings_repository
from app.modules.settings.domain.repository import SettingsRepository

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/{key}")
async def get_setting(
    key: str,
    repo: Annotated[SettingsRepository, Depends(get_settings_repository)],
) -> Any:
    value = await repo.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return {"key": key, "value": value}


@router.put("/{key}")
async def set_setting(
    key: str,
    body: dict[str, Any],
    repo: Annotated[SettingsRepository, Depends(get_settings_repository)],
) -> dict[str, str]:
    await repo.set(key, body.get("value"))
    return {"status": "ok"}


@router.delete("/{key}")
async def delete_setting(
    key: str,
    repo: Annotated[SettingsRepository, Depends(get_settings_repository)],
) -> dict[str, str]:
    deleted = await repo.delete(key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return {"status": "deleted"}


@router.get("")
async def list_settings(
    repo: Annotated[SettingsRepository, Depends(get_settings_repository)],
) -> dict[str, Any]:
    return await repo.list_all()
