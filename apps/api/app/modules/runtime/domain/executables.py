from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Literal, TypeVar, cast

from app.modules.runtime.domain.routing import (
    MissingImagePolicy,
    RuntimeDeploymentOwner,
    RuntimeResourceProfile,
)
from app.modules.types.capabilities import (
    ModelContractRef,
    PredictorMetadata,
    TrainerMetadata,
    ViewContractRef,
)


class RuntimeOperation(StrEnum):
    TRAIN = "training_routes"
    TRAIN_AND_PREDICT = "train_and_predict_routes"
    PREDICT = "prediction_routes"


@dataclass(frozen=True, slots=True)
class RuntimeRouteDefinition:
    operation: RuntimeOperation
    deployment: str
    resource_profile: RuntimeResourceProfile
    owner: RuntimeDeploymentOwner
    missing_image_policy: MissingImagePolicy
    output_contract: str | Literal["trainer_model"]


RuntimeCallable = Callable[[Any], object]
TCallable = TypeVar("TCallable", bound=RuntimeCallable)


@dataclass(frozen=True, slots=True)
class RegisteredTrainer:
    """One source for trainer metadata, executable binding, and routes."""

    metadata: TrainerMetadata
    callable: RuntimeCallable
    algo_id: str
    algo_version: str
    routes: tuple[RuntimeRouteDefinition, ...]
    train_and_predict_callable: RuntimeCallable | None = None

    @property
    def id(self) -> str:
        return self.metadata.id


@dataclass(frozen=True, slots=True)
class RegisteredPredictor:
    """One source for predictor metadata, executable binding, and routes."""

    metadata: PredictorMetadata
    callable: RuntimeCallable
    algo_id: str
    algo_version: str
    routes: tuple[RuntimeRouteDefinition, ...]

    @property
    def id(self) -> str:
        return self.metadata.id


class RuntimeRouter:
    """Module-owned decorator registry, analogous to an HTTP router."""

    def __init__(self) -> None:
        self._trainers: dict[str, RegisteredTrainer] = {}
        self._predictors: dict[str, RegisteredPredictor] = {}

    def trainer(
        self,
        *,
        id: str,
        name: str,
        input_view: ViewContractRef,
        output_model: ModelContractRef,
        predictor_ids: tuple[str, ...],
        algo_id: str,
        algo_version: str,
        routes: tuple[RuntimeRouteDefinition, ...],
    ) -> Callable[[TCallable], TCallable]:
        def decorator(func: TCallable) -> TCallable:
            if id in self._trainers:
                raise RuntimeError(f"Duplicate trainer registration: {id}")
            operations = {route.operation for route in routes}
            if RuntimeOperation.TRAIN not in operations:
                raise RuntimeError(f"Trainer {id!r} must declare a training route")
            unexpected = operations - {
                RuntimeOperation.TRAIN,
                RuntimeOperation.TRAIN_AND_PREDICT,
            }
            if unexpected:
                raise RuntimeError(
                    f"Trainer {id!r} declares invalid routes: "
                    f"{sorted(item.value for item in unexpected)}"
                )
            self._trainers[id] = RegisteredTrainer(
                metadata=TrainerMetadata(
                    id=id,
                    name=name,
                    input_view=input_view,
                    output_model=output_model,
                    predictor_ids=predictor_ids,
                ),
                callable=func,
                algo_id=algo_id,
                algo_version=algo_version,
                routes=routes,
            )
            return func

        return decorator

    def predictor(
        self,
        *,
        id: str,
        name: str,
        input_view: ViewContractRef,
        input_model: ModelContractRef,
        algo_id: str,
        algo_version: str,
        routes: tuple[RuntimeRouteDefinition, ...],
    ) -> Callable[[TCallable], TCallable]:
        def decorator(func: TCallable) -> TCallable:
            if id in self._predictors:
                raise RuntimeError(f"Duplicate predictor registration: {id}")
            operations = {route.operation for route in routes}
            if operations != {RuntimeOperation.PREDICT}:
                raise RuntimeError(
                    f"Predictor {id!r} must declare only a prediction route"
                )
            self._predictors[id] = RegisteredPredictor(
                metadata=PredictorMetadata(
                    id=id,
                    name=name,
                    input_view=input_view,
                    input_model=input_model,
                ),
                callable=func,
                algo_id=algo_id,
                algo_version=algo_version,
                routes=routes,
            )
            return func

        return decorator

    def train_and_predict(self, *, trainer_id: str) -> Callable[[TCallable], TCallable]:
        def decorator(func: TCallable) -> TCallable:
            try:
                registration = self._trainers[trainer_id]
            except KeyError as exc:
                raise RuntimeError(
                    f"Train-and-predict registration references unknown trainer "
                    f"{trainer_id!r}"
                ) from exc
            if registration.train_and_predict_callable is not None:
                raise RuntimeError(
                    f"Duplicate train-and-predict registration: {trainer_id}"
                )
            self._trainers[trainer_id] = replace(
                registration,
                train_and_predict_callable=func,
            )
            return func

        return decorator

    def trainers(self) -> tuple[RegisteredTrainer, ...]:
        return tuple(self._trainers.values())

    def predictors(self) -> tuple[RegisteredPredictor, ...]:
        return tuple(self._predictors.values())


class RuntimeCapabilityCatalog:
    """Validated aggregate of module-owned runtime routers."""

    def __init__(
        self,
        routers: Iterable[RuntimeRouter],
        *,
        known_views: Mapping[str, ViewContractRef],
    ) -> None:
        self._trainers: dict[str, RegisteredTrainer] = {}
        self._predictors: dict[str, RegisteredPredictor] = {}
        self._routes: dict[tuple[RuntimeOperation, str], RuntimeRouteDefinition] = {}
        for router in routers:
            for trainer in router.trainers():
                self._add_trainer(trainer)
            for predictor in router.predictors():
                self._add_predictor(predictor)
        self._validate(known_views)

    def _add_trainer(self, trainer: RegisteredTrainer) -> None:
        if trainer.id in self._trainers:
            raise RuntimeError(f"Duplicate trainer registration: {trainer.id}")
        self._trainers[trainer.id] = trainer
        self._add_routes(trainer.id, trainer.routes)

    def _add_predictor(self, predictor: RegisteredPredictor) -> None:
        if predictor.id in self._predictors:
            raise RuntimeError(f"Duplicate predictor registration: {predictor.id}")
        self._predictors[predictor.id] = predictor
        self._add_routes(predictor.id, predictor.routes)

    def _add_routes(
        self,
        catalog_id: str,
        routes: tuple[RuntimeRouteDefinition, ...],
    ) -> None:
        for route in routes:
            key = (route.operation, catalog_id)
            if key in self._routes:
                raise RuntimeError(
                    f"Duplicate runtime route: {route.operation.value}.{catalog_id}"
                )
            self._routes[key] = route

    def _validate(self, known_views: Mapping[str, ViewContractRef]) -> None:
        for trainer in self._trainers.values():
            self._require_view(trainer.metadata.input_view, known_views, trainer.id)
            if not trainer.metadata.predictor_ids:
                raise RuntimeError(
                    f"Trainer {trainer.id!r} must declare at least one predictor"
                )
            if self.route_or_none(RuntimeOperation.TRAIN_AND_PREDICT, trainer.id):
                if trainer.train_and_predict_callable is None:
                    raise RuntimeError(
                        f"Trainer {trainer.id!r} declares train-and-predict routing "
                        "without an executable"
                    )
        for predictor in self._predictors.values():
            self._require_view(predictor.metadata.input_view, known_views, predictor.id)
        for trainer in self._trainers.values():
            for predictor_id in trainer.metadata.predictor_ids:
                predictor = self.get_predictor(predictor_id)
                if predictor.metadata.input_view != trainer.metadata.input_view:
                    raise RuntimeError(
                        f"Trainer {trainer.id!r} and predictor {predictor_id!r} "
                        "must use the same view contract"
                    )
                if predictor.metadata.input_model != trainer.metadata.output_model:
                    raise RuntimeError(
                        f"Trainer {trainer.id!r} and predictor {predictor_id!r} "
                        "must use the same model contract"
                    )

    @staticmethod
    def _require_view(
        ref: ViewContractRef,
        known_views: Mapping[str, ViewContractRef],
        owner: str,
    ) -> None:
        if known_views.get(ref.view_id) != ref:
            raise RuntimeError(
                f"Runtime capability {owner!r} references unknown view {ref!r}"
            )

    def list_trainers(self) -> tuple[TrainerMetadata, ...]:
        return tuple(item.metadata for item in self._trainers.values())

    def list_predictors(self) -> tuple[PredictorMetadata, ...]:
        return tuple(item.metadata for item in self._predictors.values())

    def list_trainer_ids(self) -> list[str]:
        return list(self._trainers)

    def list_predictor_ids(self) -> list[str]:
        return list(self._predictors)

    def get_trainer(self, trainer_id: str) -> RegisteredTrainer:
        try:
            return self._trainers[trainer_id]
        except KeyError as exc:
            raise KeyError(f"Unknown trainer capability: {trainer_id}") from exc

    def get_predictor(self, predictor_id: str) -> RegisteredPredictor:
        try:
            return self._predictors[predictor_id]
        except KeyError as exc:
            raise KeyError(f"Unknown predictor capability: {predictor_id}") from exc

    def get_trainer_meta(self, trainer_id: str) -> TrainerMetadata:
        return self.get_trainer(trainer_id).metadata

    def get_predictor_meta(self, predictor_id: str) -> PredictorMetadata:
        return self.get_predictor(predictor_id).metadata

    def resolve_predictor_id(
        self,
        trainer_id: str,
        *,
        requested_predictor_id: str | None = None,
    ) -> str:
        trainer = self.get_trainer_meta(trainer_id)
        if requested_predictor_id is not None:
            if requested_predictor_id not in trainer.predictor_ids:
                raise ValueError(
                    f"Predictor {requested_predictor_id!r} is not paired with "
                    f"trainer {trainer_id!r}"
                )
            return requested_predictor_id
        return trainer.predictor_id

    def validate_predictor_model_contract(
        self,
        predictor_id: str,
        *,
        model_contract: object,
        model_schema_version: object,
    ) -> PredictorMetadata:
        predictor = self.get_predictor_meta(predictor_id)
        if (
            model_contract != predictor.input_model.contract
            or model_schema_version != predictor.input_model.schema_version
        ):
            raise ValueError(
                f"Model contract {model_contract!r}/{model_schema_version!r} "
                f"is incompatible with predictor {predictor_id!r} contract "
                f"{predictor.input_model.contract!r}/"
                f"{predictor.input_model.schema_version!r}"
            )
        return predictor

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

    def route_or_none(
        self,
        operation: RuntimeOperation,
        catalog_id: str,
    ) -> RuntimeRouteDefinition | None:
        return self._routes.get((operation, catalog_id))

    def registration_for(
        self,
        operation: RuntimeOperation,
        catalog_id: str,
    ) -> RegisteredTrainer | RegisteredPredictor:
        if operation is RuntimeOperation.PREDICT:
            return self.get_predictor(catalog_id)
        return self.get_trainer(catalog_id)

    def callable_for(
        self,
        operation: RuntimeOperation,
        catalog_id: str,
    ) -> RuntimeCallable:
        registration = self.registration_for(operation, catalog_id)
        if operation is RuntimeOperation.TRAIN_AND_PREDICT:
            workflow = cast(RegisteredTrainer, registration).train_and_predict_callable
            if workflow is None:
                raise KeyError(
                    f"Trainer {catalog_id!r} has no train-and-predict executable"
                )
            return workflow
        return registration.callable

    async def invoke(
        self,
        operation: RuntimeOperation,
        catalog_id: str,
        context: object,
    ) -> object:
        result = self.callable_for(operation, catalog_id)(context)
        if inspect.isawaitable(result):
            return await cast(Awaitable[object], result)
        return result

    def list_routes(
        self,
    ) -> tuple[tuple[str, RuntimeRouteDefinition], ...]:
        return tuple(
            (catalog_id, route)
            for (operation, catalog_id), route in self._routes.items()
        )


__all__ = [
    "RegisteredPredictor",
    "RegisteredTrainer",
    "RuntimeCapabilityCatalog",
    "RuntimeOperation",
    "RuntimeRouteDefinition",
    "RuntimeRouter",
]
