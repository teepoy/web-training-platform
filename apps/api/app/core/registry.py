from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from app.modules.types import catalog

T_co = TypeVar("T_co", contravariant=True)
R = TypeVar("R", covariant=True)


@dataclass
class Trainer(Generic[T_co, R]):
    trainer_id: str
    name: str
    view_id: str
    func: Callable[..., Any]

    async def __call__(self, *args: Any, **kwargs: Any) -> R:
        result = self.func(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


@dataclass
class Predictor(Generic[T_co, R]):
    predictor_id: str
    name: str
    view_id: str
    func: Callable[..., Any]

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        result = self.func(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


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
    """Central type registry.

    Holds three registration namespaces:

    * ``_views`` — view types (``@view`` decorator), API-side always populated.
    * ``_trainers`` — **executable** trainer registrations. Runtime code may
      populate these by importing executable modules; catalog declarations never
      import executable modules.
    * ``_predictors`` — **executable** predictor registrations. Same semantics
      as ``_trainers``: only entries registered via ``@predictor`` decorator
      are executable.

    Metadata-only lookups (for API listing / compatibility) go through
    :mod:`app.modules.types.catalog`, NOT through the executable dicts.
    """

    def __init__(self) -> None:
        self._views: dict[str, type] = {}
        self._trainers: dict[str, Trainer[Any, Any]] = {}
        self._predictors: dict[str, Predictor[Any, Any]] = {}

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

    def register_trainer(
        self,
        func: Callable[..., Any] | None = None,
        *,
        id: str,
        name: str | None = None,
        view_id: str | None = None,
    ) -> Any:
        if func is None:
            return functools.partial(
                self.register_trainer, id=id, name=name, view_id=view_id
            )
        try:
            metadata = catalog.get_trainer_meta(id)
        except KeyError as exc:
            raise ValueError(
                f"Executable trainer '{id}' has no API catalog metadata"
            ) from exc
        if name is not None and name != metadata.name:
            raise ValueError(
                f"Executable trainer '{id}' name does not match catalog: "
                f"{name!r} != {metadata.name!r}"
            )
        if view_id is not None and view_id != metadata.view_id:
            raise ValueError(
                f"Executable trainer '{id}' view does not match catalog: "
                f"{view_id!r} != {metadata.view_id!r}"
            )
        instance = Trainer[Any, Any](
            trainer_id=id,
            name=metadata.name,
            view_id=metadata.view_id,
            func=func,
        )
        self._trainers[id] = instance
        return instance

    def get_trainer_by_id(self, trainer_id: str) -> Trainer[Any, Any] | None:
        return self._trainers.get(trainer_id)

    def get_trainer(self, trainer_id: str) -> Trainer[Any, Any] | None:
        return self.get_trainer_by_id(trainer_id)

    def list_trainers(self) -> list[dict[str, Any]]:
        return [
            {
                "id": t.trainer_id,
                "name": t.name,
                "view_type": t.view_id,
            }
            for t in self._trainers.values()
        ]

    def register_predictor(
        self,
        func: Callable[..., Any] | None = None,
        *,
        id: str,
        name: str | None = None,
        view_id: str | None = None,
    ) -> Any:
        if func is None:
            return functools.partial(
                self.register_predictor, id=id, name=name, view_id=view_id
            )
        try:
            metadata = catalog.get_predictor_meta(id)
        except KeyError as exc:
            raise ValueError(
                f"Executable predictor '{id}' has no API catalog metadata"
            ) from exc
        if name is not None and name != metadata.name:
            raise ValueError(
                f"Executable predictor '{id}' name does not match catalog: "
                f"{name!r} != {metadata.name!r}"
            )
        if view_id is not None and view_id != metadata.view_id:
            raise ValueError(
                f"Executable predictor '{id}' view does not match catalog: "
                f"{view_id!r} != {metadata.view_id!r}"
            )
        setattr(func, "_view_id", metadata.view_id)
        instance = Predictor[Any, Any](
            predictor_id=id,
            name=metadata.name,
            view_id=metadata.view_id,
            func=func,
        )
        self._predictors[id] = instance
        return instance

    def get_predictor(self, predictor_id: str) -> Predictor[Any, Any]:
        """Return an **executable** predictor by ID.

        Only returns predictors registered via ``@predictor`` decorator.
        Metadata-only queries belong to :mod:`app.modules.types.catalog`.

        Raises:
            KeyError: No executable predictor registered for *predictor_id*.
        """
        predictor = self._predictors.get(predictor_id)
        if predictor is None:
            raise KeyError(
                f"No executable predictor registered for '{predictor_id}'. "
                f"Use catalog.get_predictor_meta() for metadata-only lookups, "
                f"or ensure the predictor module is imported in the worker runtime."
            )
        return predictor

    def get_predictor_by_id(self, predictor_id: str) -> Predictor[Any, Any] | None:
        return self._predictors.get(predictor_id)

    def list_predictors(self) -> list[dict[str, Any]]:
        return [
            {
                "id": p.predictor_id,
                "name": p.name,
                "view_type": p.view_id,
            }
            for p in self._predictors.values()
        ]


_registry = _Registry()

view = _registry.register_view
trainer = _registry.register_trainer
predictor = _registry.register_predictor

get_view = _registry.get_view
list_views = _registry.list_views
get_trainer = _registry.get_trainer
get_trainer_by_id = _registry.get_trainer_by_id
list_trainers = _registry.list_trainers
get_predictor = _registry.get_predictor
get_predictor_by_id = _registry.get_predictor_by_id
list_predictors = _registry.list_predictors

resolve_task_type = resolve_task_type
get_dataset_adapter = get_dataset_adapter
get_dataset_model = get_dataset_model
validate_dataset_task = validate_dataset_task
list_dataset_types = list_dataset_types
