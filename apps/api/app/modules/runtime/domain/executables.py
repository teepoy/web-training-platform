from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.modules.runtime.domain.routing import (
    MissingImagePolicy,
    RuntimeDeploymentOwner,
    RuntimeResourceProfile,
)


class ExecutableKind(StrEnum):
    TRAINER = "trainer"
    PREDICTOR = "predictor"


class RuntimeOperation(StrEnum):
    TRAIN = "training_routes"
    TRAIN_AND_PREDICT = "train_and_predict_routes"
    PREDICT = "prediction_routes"


@dataclass(frozen=True, slots=True)
class LocalExecutableBinding:
    """Lazy module binding for an executable owned by an API module."""

    kind: ExecutableKind
    catalog_id: str
    module: str


@dataclass(frozen=True, slots=True)
class RuntimeRouteDefinition:
    operation: RuntimeOperation
    deployment: str
    resource_profile: RuntimeResourceProfile
    owner: RuntimeDeploymentOwner
    missing_image_policy: MissingImagePolicy
    output_contract: str | Literal["trainer_model"]


@dataclass(frozen=True, slots=True)
class RuntimeExecutableDefinition:
    catalog_id: str
    algo_id: str
    algo_version: str
    trainer_module: str
    predictor_module: str
    routes: tuple[RuntimeRouteDefinition, ...]


@dataclass(frozen=True, slots=True)
class RuntimeCapabilityBundle:
    executables: tuple[RuntimeExecutableDefinition, ...]


class RuntimeCapabilityCatalog:
    def __init__(self, bundles: tuple[RuntimeCapabilityBundle, ...]) -> None:
        self._executables: dict[str, RuntimeExecutableDefinition] = {}
        self._routes: dict[tuple[RuntimeOperation, str], RuntimeRouteDefinition] = {}
        for bundle in bundles:
            for executable in bundle.executables:
                if executable.catalog_id in self._executables:
                    raise RuntimeError(
                        f"Duplicate runtime capability: {executable.catalog_id}"
                    )
                self._executables[executable.catalog_id] = executable
                for route in executable.routes:
                    key = (route.operation, executable.catalog_id)
                    if key in self._routes:
                        raise RuntimeError(
                            "Duplicate runtime route: "
                            f"{route.operation.value}.{executable.catalog_id}"
                        )
                    self._routes[key] = route

    def list(self) -> tuple[LocalExecutableBinding, ...]:
        return tuple(
            binding
            for executable in self._executables.values()
            for binding in (
                LocalExecutableBinding(
                    kind=ExecutableKind.TRAINER,
                    catalog_id=executable.catalog_id,
                    module=executable.trainer_module,
                ),
                LocalExecutableBinding(
                    kind=ExecutableKind.PREDICTOR,
                    catalog_id=executable.catalog_id,
                    module=executable.predictor_module,
                ),
            )
        )

    def get(self, kind: ExecutableKind, catalog_id: str) -> LocalExecutableBinding:
        try:
            executable = self._executables[catalog_id]
        except KeyError as exc:
            raise KeyError(
                f"{kind.value}_id={catalog_id!r} has no local executable binding"
            ) from exc
        module = (
            executable.trainer_module
            if kind is ExecutableKind.TRAINER
            else executable.predictor_module
        )
        return LocalExecutableBinding(kind=kind, catalog_id=catalog_id, module=module)

    def executable(self, catalog_id: str) -> RuntimeExecutableDefinition:
        try:
            return self._executables[catalog_id]
        except KeyError as exc:
            raise KeyError(f"Unknown runtime capability: {catalog_id}") from exc

    def route(
        self,
        operation: RuntimeOperation,
        catalog_id: str,
    ) -> RuntimeRouteDefinition:
        try:
            return self._routes[(operation, catalog_id)]
        except KeyError as exc:
            raise KeyError(
                f"No runtime route for {operation.value}.{catalog_id}"
            ) from exc

    def list_routes(
        self,
    ) -> tuple[tuple[str, RuntimeRouteDefinition], ...]:
        return tuple(
            (catalog_id, route)
            for (operation, catalog_id), route in self._routes.items()
        )
