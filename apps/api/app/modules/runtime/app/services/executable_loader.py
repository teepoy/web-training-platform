from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from app.core.registry import (
    Trainer,
    get_predictor as get_registered_predictor,
    get_trainer as get_registered_trainer,
)
from app.modules.runtime.domain.executables import (
    ExecutableKind,
    LocalExecutableBinding,
)
from app.modules.runtime.catalog import runtime_capabilities
from app.modules.types import catalog


def list_local_executable_bindings() -> tuple[LocalExecutableBinding, ...]:
    return runtime_capabilities.list()


def validate_local_executable_bindings() -> None:
    predictor_ids = {
        binding.catalog_id
        for binding in runtime_capabilities.list()
        if binding.kind is ExecutableKind.PREDICTOR
    }
    for binding in runtime_capabilities.list():
        if binding.kind is ExecutableKind.TRAINER:
            trainer = catalog.get_trainer_meta(binding.catalog_id)
            missing = set(trainer.predictor_ids) - predictor_ids
            if missing:
                raise RuntimeError(
                    f"Local trainer {trainer.id!r} is missing predictor bindings: "
                    f"{sorted(missing)}"
                )
        else:
            catalog.get_predictor_meta(binding.catalog_id)


def get_trainer(trainer_id: str) -> Trainer[object, object]:
    catalog.get_trainer_meta(trainer_id)
    binding = runtime_capabilities.get(ExecutableKind.TRAINER, trainer_id)
    importlib.import_module(binding.module)
    registered = get_registered_trainer(trainer_id)
    if registered is None:
        raise KeyError(
            f"trainer_id={trainer_id!r} was imported but did not register an executable"
        )
    return registered


def get_predictor(predictor_id: str) -> Callable[..., Any]:
    catalog.get_predictor_meta(predictor_id)
    binding = runtime_capabilities.get(ExecutableKind.PREDICTOR, predictor_id)
    importlib.import_module(binding.module)
    registered = get_registered_predictor(predictor_id)
    return registered.func
