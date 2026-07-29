from __future__ import annotations

import importlib
from dataclasses import dataclass
from enum import StrEnum

from app.modules.types import catalog


class ExecutableKind(StrEnum):
    TRAINER = "trainer"
    PREDICTOR = "predictor"


@dataclass(frozen=True, slots=True)
class LocalExecutableBinding:
    """Worker-only compatibility binding for an executable implementation."""

    kind: ExecutableKind
    catalog_id: str
    module: str


_LOCAL_EXECUTABLE_BINDINGS = (
    LocalExecutableBinding(
        kind=ExecutableKind.TRAINER,
        catalog_id="resnet50-sc-v1",
        module="app.runtime_compat.ml.trainers.sc",
    ),
    LocalExecutableBinding(
        kind=ExecutableKind.TRAINER,
        catalog_id="yolo-sc-v1",
        module="app.runtime_compat.ml.trainers.yolo_sc",
    ),
    LocalExecutableBinding(
        kind=ExecutableKind.PREDICTOR,
        catalog_id="resnet50-sc-v1",
        module="app.runtime_compat.ml.predictors.sc",
    ),
    LocalExecutableBinding(
        kind=ExecutableKind.PREDICTOR,
        catalog_id="yolo-sc-v1",
        module="app.runtime_compat.ml.predictors.yolo_sc",
    ),
)

_BINDING_INDEX = {
    (binding.kind, binding.catalog_id): binding
    for binding in _LOCAL_EXECUTABLE_BINDINGS
}


def list_local_executable_bindings() -> tuple[LocalExecutableBinding, ...]:
    return _LOCAL_EXECUTABLE_BINDINGS


def import_local_executable(kind: ExecutableKind, catalog_id: str) -> None:
    binding = _BINDING_INDEX.get((kind, catalog_id))
    if binding is None:
        raise KeyError(
            f"{kind.value}_id={catalog_id!r} has no worker-local executable binding"
        )
    importlib.import_module(binding.module)


def validate_local_executable_bindings() -> None:
    seen: set[tuple[ExecutableKind, str]] = set()
    for binding in _LOCAL_EXECUTABLE_BINDINGS:
        key = (binding.kind, binding.catalog_id)
        if key in seen:
            raise RuntimeError(
                f"Duplicate worker-local executable binding: "
                f"{binding.kind.value}:{binding.catalog_id}"
            )
        seen.add(key)
        try:
            if binding.kind is ExecutableKind.TRAINER:
                catalog.get_trainer_meta(binding.catalog_id)
            else:
                catalog.get_predictor_meta(binding.catalog_id)
        except KeyError as exc:
            raise RuntimeError(
                f"Worker-local executable binding has no catalog metadata: "
                f"{binding.kind.value}:{binding.catalog_id}"
            ) from exc

    predictor_ids = {
        binding.catalog_id
        for binding in _LOCAL_EXECUTABLE_BINDINGS
        if binding.kind is ExecutableKind.PREDICTOR
    }
    for binding in _LOCAL_EXECUTABLE_BINDINGS:
        if binding.kind is not ExecutableKind.TRAINER:
            continue
        trainer = catalog.get_trainer_meta(binding.catalog_id)
        missing_predictors = set(trainer.predictor_ids) - predictor_ids
        if missing_predictors:
            raise RuntimeError(
                f"Worker-local trainer {trainer.id!r} is missing paired predictor "
                f"bindings: {sorted(missing_predictors)}"
            )


validate_local_executable_bindings()
