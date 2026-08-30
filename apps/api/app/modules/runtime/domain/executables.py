from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast, runtime_checkable

from app.modules.runtime.domain.context import (
    PredictionRuntimeContext,
    TrainAndPredictRuntimeContext,
    TrainingRuntimeContext,
)
from app.modules.runtime.domain.events import RuntimeEventStream
from app.modules.types.capabilities import (
    ModelContractRef,
    PredictorMetadata,
    TrainerMetadata,
    ViewContractRef,
)


TrainCallable = Callable[[TrainingRuntimeContext], RuntimeEventStream]
PredictCallable = Callable[[PredictionRuntimeContext], RuntimeEventStream]
TrainAndPredictCallable = Callable[[TrainAndPredictRuntimeContext], RuntimeEventStream]
ModelArtifactValidator = Callable[[Path, str], None]

TTrainCallable = TypeVar("TTrainCallable", bound=TrainCallable)
TPredictCallable = TypeVar("TPredictCallable", bound=PredictCallable)
TTrainAndPredictCallable = TypeVar(
    "TTrainAndPredictCallable",
    bound=TrainAndPredictCallable,
)
TAlgorithmClass = TypeVar("TAlgorithmClass", bound=type[Any])


@runtime_checkable
class Trainable(Protocol):
    @staticmethod
    def train(ctx: TrainingRuntimeContext) -> RuntimeEventStream: ...


@runtime_checkable
class Predictable(Protocol):
    @staticmethod
    def predict(ctx: PredictionRuntimeContext) -> RuntimeEventStream: ...


@runtime_checkable
class TrainAndPredictable(Protocol):
    @staticmethod
    def train_and_predict(
        ctx: TrainAndPredictRuntimeContext,
    ) -> RuntimeEventStream: ...


@dataclass(frozen=True, slots=True)
class RegisteredTrainer:
    """One source for trainer metadata, executable binding, and identity."""

    metadata: TrainerMetadata
    callable: TrainCallable
    algo_id: str
    algo_version: str
    artifact_validator: ModelArtifactValidator
    train_and_predict_callable: TrainAndPredictCallable | None = None

    @property
    def id(self) -> str:
        return self.metadata.id


@dataclass(frozen=True, slots=True)
class RegisteredPredictor:
    """One source for predictor metadata, executable binding, and identity."""

    metadata: PredictorMetadata
    callable: PredictCallable
    algo_id: str
    algo_version: str

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
        artifact_validator: ModelArtifactValidator,
    ) -> Callable[[TTrainCallable], TTrainCallable]:
        def decorator(func: TTrainCallable) -> TTrainCallable:
            if id in self._trainers:
                raise RuntimeError(f"Duplicate trainer registration: {id}")
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
                artifact_validator=artifact_validator,
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
    ) -> Callable[[TPredictCallable], TPredictCallable]:
        def decorator(func: TPredictCallable) -> TPredictCallable:
            if id in self._predictors:
                raise RuntimeError(f"Duplicate predictor registration: {id}")
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
            )
            return func

        return decorator

    def algorithm(
        self,
        *,
        id: str,
        trainer_name: str,
        predictor_name: str,
        input_view: ViewContractRef,
        model: ModelContractRef,
        algo_id: str,
        algo_version: str,
        artifact_validator: ModelArtifactValidator,
    ) -> Callable[[TAlgorithmClass], TAlgorithmClass]:
        """Register a paired algorithm and derive operations from its Protocols."""

        def decorator(algorithm_cls: TAlgorithmClass) -> TAlgorithmClass:
            if not isinstance(algorithm_cls, Trainable):
                raise RuntimeError(f"Runtime algorithm {id!r} must implement Trainable")
            if not isinstance(algorithm_cls, Predictable):
                raise RuntimeError(
                    f"Runtime algorithm {id!r} must implement Predictable"
                )
            if id in self._trainers or id in self._predictors:
                raise RuntimeError(f"Duplicate runtime algorithm registration: {id}")

            self.trainer(
                id=id,
                name=trainer_name,
                input_view=input_view,
                output_model=model,
                predictor_ids=(id,),
                algo_id=algo_id,
                algo_version=algo_version,
                artifact_validator=artifact_validator,
            )(cast(TrainCallable, algorithm_cls.train))
            self.predictor(
                id=id,
                name=predictor_name,
                input_view=input_view,
                input_model=model,
                algo_id=algo_id,
                algo_version=algo_version,
            )(cast(PredictCallable, algorithm_cls.predict))
            if isinstance(algorithm_cls, TrainAndPredictable):
                self.train_and_predict(trainer_id=id)(
                    cast(
                        TrainAndPredictCallable,
                        algorithm_cls.train_and_predict,
                    )
                )
            return algorithm_cls

        return decorator

    def train_and_predict(
        self,
        *,
        trainer_id: str,
    ) -> Callable[[TTrainAndPredictCallable], TTrainAndPredictCallable]:
        def decorator(func: TTrainAndPredictCallable) -> TTrainAndPredictCallable:
            try:
                registration = self._trainers[trainer_id]
            except KeyError as exc:
                raise RuntimeError(
                    "Train-and-predict registration references unknown trainer "
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

    def _add_predictor(self, predictor: RegisteredPredictor) -> None:
        if predictor.id in self._predictors:
            raise RuntimeError(f"Duplicate predictor registration: {predictor.id}")
        self._predictors[predictor.id] = predictor

    def _validate(self, known_views: Mapping[str, ViewContractRef]) -> None:
        for trainer in self._trainers.values():
            self._require_view(trainer.metadata.input_view, known_views, trainer.id)
            if not trainer.metadata.predictor_ids:
                raise RuntimeError(
                    f"Trainer {trainer.id!r} must declare at least one predictor"
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

    def supports_train_and_predict(self, trainer_id: str) -> bool:
        return self.get_trainer(trainer_id).train_and_predict_callable is not None

    def stream_train(
        self,
        trainer_id: str,
        context: TrainingRuntimeContext,
    ) -> RuntimeEventStream:
        return self.get_trainer(trainer_id).callable(context)

    def stream_predict(
        self,
        predictor_id: str,
        context: PredictionRuntimeContext,
    ) -> RuntimeEventStream:
        return self.get_predictor(predictor_id).callable(context)

    def stream_train_and_predict(
        self,
        trainer_id: str,
        context: TrainAndPredictRuntimeContext,
    ) -> RuntimeEventStream:
        callable_ = self.get_trainer(trainer_id).train_and_predict_callable
        if callable_ is None:
            raise KeyError(
                f"Trainer {trainer_id!r} has no train-and-predict executable"
            )
        return callable_(context)


__all__ = [
    "Predictable",
    "RegisteredPredictor",
    "RegisteredTrainer",
    "RuntimeCapabilityCatalog",
    "RuntimeRouter",
    "TrainAndPredictable",
    "Trainable",
]
