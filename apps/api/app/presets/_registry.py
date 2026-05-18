"""Preset registry — decorator-based registration.

Each preset is a single Python module decorated with :func:`register`.
The registry holds preset metadata (compatibility, scheduling, model info)
and entrypoint references (trainer, predictor, pipeline classes).

No YAML — all config lives in the preset module and its imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _PresetMeta:
    """Metadata for one registered preset."""

    id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    trainable: bool = True

    # Compatibility — which dataset types this preset accepts
    dataset_types: list[str] = field(default_factory=list)
    task_types: list[str] = field(default_factory=list)
    prediction_targets: list[str] = field(default_factory=list)

    # Scheduling
    queue: str = "default"
    resources: dict[str, Any] = field(default_factory=dict)

    # Model identity (for API display and artifact provenance)
    model: dict[str, Any] = field(default_factory=dict)

    # Deprecation
    deprecated: bool = False
    compat_min_api_version: str | None = None

    # Ownership
    team: str = ""
    maintainer: str = ""


_registry: dict[str, type] = {}


def register(
    *,
    id: str,
    name: str,
    version: str = "0.1.0",
    description: str = "",
    tags: list[str] | None = None,
    trainable: bool = True,
    dataset_types: list[str] | None = None,
    task_types: list[str] | None = None,
    prediction_targets: list[str] | None = None,
    queue: str = "default",
    resources: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
    deprecated: bool = False,
    compat_min_api_version: str | None = None,
    team: str = "",
    maintainer: str = "",
):
    """Decorator that registers a preset class.

    The decorated class provides ``train()``, ``predict()``, and
    ``pipeline()`` static/class methods (or instance methods) that
    collectively define the preset's complete behaviour.

    Usage::

        @register(id="my-v1", name="My Preset", ...)
        class MyPreset:
            @staticmethod
            def train(context): ...
            @staticmethod
            def predict(target, model_uri): ...
            @staticmethod
            def pipeline(): ...
    """
    meta = _PresetMeta(
        id=id,
        name=name,
        version=version,
        description=description,
        tags=tags or [],
        trainable=trainable,
        dataset_types=dataset_types or [],
        task_types=task_types or [],
        prediction_targets=prediction_targets or [],
        queue=queue,
        resources=resources or {},
        model=model or {},
        deprecated=deprecated,
        compat_min_api_version=compat_min_api_version,
        team=team,
        maintainer=maintainer,
    )

    def decorator(cls):
        cls._preset_meta = meta  # type: ignore[attr-defined]
        _registry[id] = cls
        return cls

    return decorator


def get_preset(preset_id: str) -> type | None:
    """Return the registered preset class for *preset_id*, or ``None``."""
    return _registry.get(preset_id)


def get_preset_meta(preset_id: str) -> _PresetMeta | None:
    """Return metadata for *preset_id*, or ``None``."""
    cls = _registry.get(preset_id)
    if cls is None:
        return None
    return getattr(cls, "_preset_meta", None)


def list_presets(*, include_deprecated: bool = False) -> list[_PresetMeta]:
    """Return metadata for all registered presets."""
    result: list[_PresetMeta] = []
    for cls in _registry.values():
        meta = getattr(cls, "_preset_meta", None)
        if meta is None:
            continue
        if not include_deprecated and meta.deprecated:
            continue
        result.append(meta)
    return result


def preset_meta_to_api_dict(meta: _PresetMeta) -> dict[str, Any]:
    """Convert preset metadata to the legacy API response shape.

    Keeps frontend/sdk compatibility during migration.
    """
    return {
        "id": meta.id,
        "name": meta.name,
        "version": meta.version,
        "description": meta.description,
        "tags": meta.tags,
        "deprecated": meta.deprecated,
        "trainable": meta.trainable,
        "model": meta.model,
        "compatibility": {
            "dataset_types": list(meta.dataset_types),
            "task_types": list(meta.task_types),
            "prediction_targets": list(meta.prediction_targets),
        },
        "runtime": {
            "queue": meta.queue,
            "resources": meta.resources,
        },
        "ownership": {
            "team": meta.team,
            "maintainer": meta.maintainer,
        },
        # Legacy fields for frontend compat
        "model_spec": {
            "framework": meta.model.get("framework", ""),
            "base_model": meta.model.get("base_model", ""),
        },
        "omegaconf_yaml": "",
        "dataloader_ref": "",
        "org_id": None,
        "train": {"entrypoint": "", "config": {}, "dataloader": None},
        "predict": {"entrypoint": "", "config": {}, "targets": {}},
        "test": None,
        "convert": None,
    }
