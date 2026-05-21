from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.presets.registry import PresetRegistry


def get_preset_registry(request: Request) -> PresetRegistry:
    return request.app.state.container.preset_registry


PresetRegistryDep = Annotated[PresetRegistry, Depends(get_preset_registry)]
