from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any

from app.modules.types import catalog


@dataclass
class DatasetTypeRegistration:
    dataset_type: str
    view_types: list[str]
    task_type: str
    adapter_class: type

    @property
    def model_class(self) -> type:
        return self.adapter_class

    def create_adapter(self) -> Any:
        return self.adapter_class()


_dataset_view_types: dict[str, list[str]] = {
    "image_classification": ["image_input_v1", "labeled_image_v1"],
}


_dataset_type_registry: dict[str, DatasetTypeRegistration] = {}


def register_dataset_type(reg: DatasetTypeRegistration) -> None:
    if reg.dataset_type in _dataset_type_registry:
        raise ValueError(f"Dataset type '{reg.dataset_type}' is already registered")
    unknown_views: list[str] = []
    for view_id in reg.view_types:
        try:
            catalog.get_view_meta(view_id)
        except KeyError:
            unknown_views.append(view_id)
    if unknown_views:
        raise ValueError(
            f"Dataset type {reg.dataset_type!r} references unknown catalog views: "
            f"{sorted(unknown_views)}"
        )
    _dataset_type_registry[reg.dataset_type] = reg


def dataset(
    cls: type | None = None,
    *,
    dataset_type: str | None = None,
    view_types: list[str] | None = None,
    task_type: str | None = None,
) -> Any:
    if cls is not None:
        return _register_from_classvar(cls)
    if dataset_type is not None:

        def decorator(c: type) -> type:
            return _register_explicit(
                c,
                dataset_type=dataset_type,
                view_types=view_types or [],
                task_type=task_type or "unknown",
            )

        return decorator
    raise TypeError(
        "@dataset requires either no-args (ClassVar) or "
        "keyword args (dataset_type=..., view_types=..., task_type=...)"
    )


def _register_from_classvar(cls: type) -> type:
    ds_type: str | None = getattr(cls, "ID", None)
    if ds_type is None:
        raise TypeError(
            f"@dataset class {cls.__name__} must define 'ID: ClassVar[str]'"
        )
    vtypes: set[str] = getattr(cls, "VIEW_TYPES", set())
    task: str = getattr(cls, "TASK_TYPE", "unknown")
    return _register_explicit(
        cls,
        dataset_type=ds_type,
        view_types=list(vtypes),
        task_type=task,
    )


def _register_explicit(
    cls: type, *, dataset_type: str, view_types: list[str], task_type: str
) -> type:
    reg = DatasetTypeRegistration(
        dataset_type=dataset_type,
        view_types=view_types,
        task_type=task_type,
        adapter_class=cls,
    )
    register_dataset_type(reg)
    return cls


def get_dataset_model(dataset_type: str) -> type | None:
    reg = _dataset_type_registry.get(dataset_type)
    if reg is not None:
        return reg.model_class
    return None


def resolve_view_types(dataset_type: str) -> list[str]:
    reg = _dataset_type_registry.get(dataset_type)
    if reg is not None:
        return reg.view_types
    return _dataset_view_types.get(dataset_type, [])


def resolve_task_type(dataset_type: str) -> str | None:
    reg = _dataset_type_registry.get(dataset_type)
    if reg is not None:
        return reg.task_type
    return None


def get_dataset_adapter(dataset_type: str) -> Any | None:
    reg = _dataset_type_registry.get(dataset_type)
    if reg is not None:
        return reg.create_adapter()
    return None


def validate_dataset_task(dataset_type: str, task_type: str) -> bool:
    actual = resolve_task_type(dataset_type)
    if actual is None:
        return False
    return actual == task_type


def list_dataset_types() -> list[str]:
    return list(_dataset_type_registry.keys())


class _Registry:
    """Registry for API view row types only."""

    def __init__(self) -> None:
        self._views: dict[str, type] = {}

    def register_view(
        self,
        cls: type | None = None,
        *,
        id: str | None = None,
    ) -> Any:
        if cls is None:
            if id is None:
                raise TypeError("@view requires a catalog view id")
            return functools.partial(self.register_view, id=id)
        vid = id
        if vid is None:
            raise TypeError("@view must be called as @view(id='catalog-view-id')")
        try:
            metadata = catalog.get_view_meta(vid)
        except KeyError as exc:
            raise ValueError(
                f"View class {cls.__name__} references unknown catalog view {vid!r}"
            ) from exc
        type_path = f"{cls.__module__}:{cls.__name__}"
        if type_path != metadata.row_type_path:
            raise ValueError(
                f"View {vid!r} row type does not match catalog: "
                f"{type_path!r} != {metadata.row_type_path!r}"
            )
        cls.view_id = metadata.id
        cls.view_name = metadata.name
        cls.is_annotation_view = metadata.is_annotation_view
        existing = self._views.get(vid)
        if existing is not None and existing is not cls:
            raise ValueError(
                f"View {vid!r} is already registered by "
                f"{existing.__module__}.{existing.__name__}"
            )
        self._views[vid] = cls
        return cls

    def get_view(self, id: str) -> type | None:
        return self._views.get(id)

    def list_views(self) -> list[type]:
        return list(self._views.values())


_registry = _Registry()

view = _registry.register_view

get_view = _registry.get_view
list_views = _registry.list_views
