from __future__ import annotations

import functools
import importlib
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from app.modules.types import catalog

T_co = TypeVar("T_co", contravariant=True)
R = TypeVar("R", covariant=True)

# ── Executable module registry ─────────────────────────────────────────────
# Maps catalog trainer_id / predictor_id → executable runtime module path.
# These are lazily imported via _make_catalog_stub_* wrappers when a
# catalog-backed entry is invoked.  Modules are NOT imported at API startup;
# the API-side catalog is metadata-only per CORE_DESIGNS §6.

_TRAINER_EXECUTABLE_MODULES: dict[str, str] = {
    "yolo-sc-v1": "app.modules.training.flows._trainers.yolo_sc",
    "resnet50-sc-v1": "app.modules.training.flows._trainers.sc",
}

_PREDICTOR_EXECUTABLE_MODULES: dict[str, str] = {
    "resnet50-cls-v1": "app.modules.types.predictors.resnet",
    "dspy-vqa-v1": "app.modules.types.predictors.dspy_vqa",
    "clip-zero-shot-v1": "app.modules.types.predictors.clip",
    "detection-v1": "app.modules.types.predictors.detection",
    "yolo-sc-v1": "app.modules.prediction.flows._predictors.yolo_sc",
    "resnet50-sc-v1": "app.modules.prediction.flows._predictors.sc",
}


def _make_catalog_stub_trainer(trainer_id: str) -> Callable[..., Any]:
    """Create a catalog-backed trainer wrapper that lazily imports the executable module.

    When invoked, attempts to import the real executable module (if mapped in
    ``_TRAINER_EXECUTABLE_MODULES``) and delegates to the now-registered
    executable.  Fails with ``RuntimeError`` if no executable module exists.

    **Catalog-only stubs are NOT executable** — they exist so the API can
    enumerate trainers for listing/compatibility without importing ML deps.
    """

    async def _catalog_stub_trainer(*args: Any, **kwargs: Any) -> Any:
        module_name = _TRAINER_EXECUTABLE_MODULES.get(trainer_id)
        if module_name is not None:
            importlib.import_module(module_name)
            trainer_instance = _registry._trainers.get(trainer_id)
            if (
                trainer_instance is not None
                and trainer_instance.func is not _catalog_stub_trainer
            ):
                return await trainer_instance(*args, **kwargs)
        raise RuntimeError(
            f"Trainer '{trainer_id}' has catalog metadata but no executable "
            f"registration; load trainers in worker runtime"
        )

    return _catalog_stub_trainer


def _make_catalog_stub_predictor(predictor_id: str) -> Callable[..., Any]:
    """Create a catalog-backed predictor wrapper that lazily imports the executable module.

    When invoked, attempts to import the real executable module (if mapped in
    ``_PREDICTOR_EXECUTABLE_MODULES``) and delegates to the now-registered
    executable.  Fails with ``RuntimeError`` if no executable module exists.

    **Catalog-only stubs are NOT executable** — they exist so the API can
    enumerate predictors for listing/compatibility without importing ML deps.
    """

    def _catalog_stub_predictor(*args: Any, **kwargs: Any) -> Any:
        module_name = _PREDICTOR_EXECUTABLE_MODULES.get(predictor_id)
        if module_name is not None:
            importlib.import_module(module_name)
            predictor_instance = _registry._predictors.get(predictor_id)
            if (
                predictor_instance is not None
                and predictor_instance.func is not _catalog_stub_predictor
            ):
                return predictor_instance(*args, **kwargs)
        raise RuntimeError(
            f"Predictor '{predictor_id}' has catalog metadata but no executable "
            f"registration; load predictors in worker runtime"
        )

    return _catalog_stub_predictor


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
    "image_vqa": ["image_input_v1", "qa_input_v1"],
    "image_detection": ["image_input_v1", "box_detection_v1"],
}


_dataset_type_registry: dict[str, DatasetTypeRegistration] = {}


def register_dataset_type(reg: DatasetTypeRegistration) -> None:
    if reg.dataset_type in _dataset_type_registry:
        raise ValueError(f"Dataset type '{reg.dataset_type}' is already registered")
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
    * ``_trainers`` — **executable** trainer registrations.  May be empty at
      API startup; catalog-thru stubs are filled lazily when
      ``get_trainer_by_id`` encounters a catalog-only entry.
    * ``_predictors`` — **executable** predictor registrations.  Same
      semantics as ``_trainers``: only entries registered via ``@predictor``
      decorator are considered executable.

    Metadata-only lookups (for API listing / compatibility) go through
    :mod:`app.modules.types.catalog`, NOT through the executable dicts.
    """

    _views: dict[str, type] = {}
    _trainers: dict[str, Trainer[Any, Any]] = {}
    _predictors: dict[str, Predictor[Any, Any]] = {}

    def register_view(self, cls: type) -> type:
        vid: str | None = getattr(cls, "view_id", None)
        if vid is None:
            raise TypeError(
                f"View class {cls.__name__} must declare 'view_id: ClassVar[str]'"
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
        name: str,
        view_id: str,
    ) -> Any:
        if func is None:
            return functools.partial(
                self.register_trainer, id=id, name=name, view_id=view_id
            )
        instance = Trainer[Any, Any](
            trainer_id=id, name=name, view_id=view_id, func=func
        )
        self._trainers[id] = instance
        return instance

    def get_trainer_by_id(self, trainer_id: str) -> Trainer[Any, Any] | None:
        trainer = self._trainers.get(trainer_id)
        if trainer is not None:
            return trainer
        try:
            meta = catalog.get_trainer_meta(trainer_id)
        except KeyError:
            return None
        return Trainer[Any, Any](
            trainer_id=meta["id"],
            name=meta["name"],
            view_id=meta["view_id"],
            func=_make_catalog_stub_trainer(trainer_id),
        )

    def get_trainer(self, trainer_id: str) -> Trainer[Any, Any] | None:
        return self.get_trainer_by_id(trainer_id)

    def list_trainers(self) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for trainer_id in catalog.list_trainer_ids():
            trainer = self.get_trainer_by_id(trainer_id)
            if trainer is None:
                continue
            rows[trainer_id] = {
                "id": trainer_id,
                "name": trainer.name,
                "view_type": trainer.view_id,
            }
        for t in self._trainers.values():
            rows[t.trainer_id] = {
                "id": t.trainer_id,
                "name": t.name,
                "view_type": t.view_id,
            }
        return list(rows.values())

    def register_predictor(
        self,
        func: Callable[..., Any] | None = None,
        *,
        id: str,
        name: str,
        view_id: str,
    ) -> Any:
        if func is None:
            return functools.partial(
                self.register_predictor, id=id, name=name, view_id=view_id
            )
        setattr(func, "_view_id", view_id)
        instance = Predictor[Any, Any](
            predictor_id=id, name=name, view_id=view_id, func=func
        )
        self._predictors[id] = instance
        return instance

    def get_predictor(self, predictor_id: str) -> Predictor[Any, Any]:
        """Return an **executable** predictor by ID.

        Only returns predictors registered via ``@predictor`` decorator
        (i.e. entries in ``_predictors``).  Does NOT fall back to the
        metadata catalog — use :func:`get_predictor_by_id` (which creates
        a catalog-thru stub) or :func:`app.modules.types.catalog.get_predictor_meta`
        for metadata-only queries.

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
        predictor = self._predictors.get(predictor_id)
        if predictor is not None:
            return predictor
        try:
            meta = catalog.get_predictor_meta(predictor_id)
        except KeyError:
            return None
        return Predictor[Any, Any](
            predictor_id=meta["id"],
            name=meta["name"],
            view_id=meta["view_id"],
            func=_make_catalog_stub_predictor(predictor_id),
        )

    def list_predictors(self) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for predictor_id in catalog.list_predictor_ids():
            predictor = self.get_predictor_by_id(predictor_id)
            if predictor is None:
                continue
            rows[predictor_id] = {
                "id": predictor_id,
                "name": predictor.name,
                "view_type": predictor.view_id,
            }
        for p in self._predictors.values():
            rows[p.predictor_id] = {
                "id": p.predictor_id,
                "name": p.name,
                "view_type": p.view_id,
            }
        return list(rows.values())


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
