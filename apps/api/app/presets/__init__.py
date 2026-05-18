"""Preset package — imports all preset modules to trigger :func:`register` decorators.

Re-exports the new decorator-based registry API.
"""

from __future__ import annotations

# Import all preset modules — decorators auto-register on import
from . import resnet50_cls_v1  # noqa: F401
from . import dspy_vqa_v1  # noqa: F401
from . import clip_zero_shot_v1  # noqa: F401

# Re-export the new decorator registry API
from ._registry import (  # noqa: F401
    get_preset,
    get_preset_meta,
    list_presets,
    preset_meta_to_api_dict,
    register,
)

# Keep legacy imports working
from .registry import PresetRegistry, PresetRegistryError  # noqa: F401
from .schema import PresetSpec  # noqa: F401
