from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, TypeVar

MaterializationPurpose = Literal["train", "predict", "preview", "export"]
MaterializationFormat = Literal["parquet", "arrow_ipc", "arrow_flight"]
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ViewContractRef:
    """Stable identity shared by API views and data-plane manifests."""

    view_id: str
    contract: str
    schema_version: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.contract, self.schema_version)


@dataclass(frozen=True, slots=True)
class ModelContractRef:
    """Versioned model artifact contract shared by a trainer/predictor pair."""

    contract: str
    schema_version: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.contract, self.schema_version)


@dataclass(frozen=True, slots=True)
class ViewDefinition:
    """Import-safe definition for one versioned API/data-plane view."""

    ref: ViewContractRef
    name: str
    is_annotation_view: bool
    row_type_path: str
    arrow_schema_path: str
    image_roles: tuple[str, ...] = ()
    label_columns: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.ref.view_id


@dataclass(frozen=True, slots=True)
class MaterializerMetadata:
    """A capability that produces a versioned view manifest."""

    id: str
    output_view: ViewContractRef
    purposes: tuple[MaterializationPurpose, ...]
    formats: tuple[MaterializationFormat, ...]
    storage_modes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrainerMetadata:
    id: str
    name: str
    input_view: ViewContractRef
    output_model: ModelContractRef
    predictor_ids: tuple[str, ...]

    @property
    def view_id(self) -> str:
        return self.input_view.view_id

    @property
    def predictor_id(self) -> str:
        if len(self.predictor_ids) != 1:
            raise ValueError(
                f"Trainer {self.id!r} has {len(self.predictor_ids)} predictors; "
                "select predictor_id explicitly"
            )
        return self.predictor_ids[0]


@dataclass(frozen=True, slots=True)
class PredictorMetadata:
    id: str
    name: str
    input_view: ViewContractRef
    input_model: ModelContractRef

    @property
    def view_id(self) -> str:
        return self.input_view.view_id


@dataclass(frozen=True, slots=True)
class CapabilityBundle:
    """A module-owned declaration consumed by the central catalog."""

    views: tuple[ViewDefinition, ...] = ()
    materializers: tuple[MaterializerMetadata, ...] = ()
    trainers: tuple[TrainerMetadata, ...] = ()
    predictors: tuple[PredictorMetadata, ...] = ()


class CapabilityCatalog:
    """Immutable-by-construction aggregate of module capability bundles."""

    def __init__(self, bundles: tuple[CapabilityBundle, ...]) -> None:
        self._views = _index_unique(
            (view for bundle in bundles for view in bundle.views),
            kind="view",
        )
        self._materializers = _index_unique(
            (
                materializer
                for bundle in bundles
                for materializer in bundle.materializers
            ),
            kind="materializer",
        )
        self._trainers = _index_unique(
            (trainer for bundle in bundles for trainer in bundle.trainers),
            kind="trainer",
        )
        self._predictors = _index_unique(
            (predictor for bundle in bundles for predictor in bundle.predictors),
            kind="predictor",
        )
        self._validate_relationships()

    def list_views(self) -> tuple[ViewDefinition, ...]:
        return tuple(self._views.values())

    def list_materializers(self) -> tuple[MaterializerMetadata, ...]:
        return tuple(self._materializers.values())

    def list_trainers(self) -> tuple[TrainerMetadata, ...]:
        return tuple(self._trainers.values())

    def list_predictors(self) -> tuple[PredictorMetadata, ...]:
        return tuple(self._predictors.values())

    def get_view(self, view_id: str) -> ViewDefinition:
        return _get(self._views, view_id, kind="view")

    def get_materializer(self, materializer_id: str) -> MaterializerMetadata:
        return _get(self._materializers, materializer_id, kind="materializer")

    def get_trainer(self, trainer_id: str) -> TrainerMetadata:
        return _get(self._trainers, trainer_id, kind="trainer")

    def get_predictor(self, predictor_id: str) -> PredictorMetadata:
        return _get(self._predictors, predictor_id, kind="predictor")

    def resolve_predictor_id(
        self,
        trainer_id: str,
        *,
        requested_predictor_id: str | None = None,
    ) -> str:
        trainer = self.get_trainer(trainer_id)
        if requested_predictor_id is not None:
            if requested_predictor_id not in trainer.predictor_ids:
                raise ValueError(
                    f"Predictor {requested_predictor_id!r} is not paired with "
                    f"trainer {trainer_id!r}"
                )
            return requested_predictor_id
        if len(trainer.predictor_ids) != 1:
            raise ValueError(
                f"Trainer {trainer_id!r} has multiple paired predictors; "
                "predictor_id must be selected explicitly"
            )
        return trainer.predictor_ids[0]

    def validate_predictor_model_contract(
        self,
        predictor_id: str,
        *,
        model_contract: object,
        model_schema_version: object,
    ) -> PredictorMetadata:
        predictor = self.get_predictor(predictor_id)
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

    def materializers_for(
        self,
        view_id: str,
        *,
        purpose: MaterializationPurpose,
        storage_mode: str,
    ) -> tuple[MaterializerMetadata, ...]:
        self.get_view(view_id)
        return tuple(
            materializer
            for materializer in self._materializers.values()
            if materializer.output_view.view_id == view_id
            and purpose in materializer.purposes
            and storage_mode in materializer.storage_modes
        )

    def _validate_relationships(self) -> None:
        contract_keys: dict[tuple[str, str], str] = {}
        for view in self._views.values():
            existing = contract_keys.get(view.ref.key)
            if existing is not None:
                raise ValueError(
                    f"View contract {view.ref.key!r} is declared by both "
                    f"{existing!r} and {view.id!r}"
                )
            contract_keys[view.ref.key] = view.id

        for materializer in self._materializers.values():
            self._require_known_view(
                materializer.output_view,
                owner=f"Materializer {materializer.id!r}",
            )

        for predictor in self._predictors.values():
            self._require_known_view(
                predictor.input_view,
                owner=f"Predictor {predictor.id!r}",
            )

        for trainer in self._trainers.values():
            self._require_known_view(
                trainer.input_view,
                owner=f"Trainer {trainer.id!r}",
            )
            if not trainer.predictor_ids:
                raise ValueError(
                    f"Trainer {trainer.id!r} must declare at least one predictor"
                )
            for predictor_id in trainer.predictor_ids:
                predictor = self.get_predictor(predictor_id)
                if predictor.input_view != trainer.input_view:
                    raise ValueError(
                        f"Trainer {trainer.id!r} and predictor {predictor_id!r} "
                        "must consume the same versioned view contract"
                    )
                if predictor.input_model != trainer.output_model:
                    raise ValueError(
                        f"Trainer {trainer.id!r} produces model contract "
                        f"{trainer.output_model!r}, but predictor "
                        f"{predictor_id!r} consumes {predictor.input_model!r}"
                    )

    def _require_known_view(self, ref: ViewContractRef, *, owner: str) -> None:
        registered = self.get_view(ref.view_id)
        if registered.ref != ref:
            raise ValueError(
                f"{owner} references {ref!r}, but catalog declares {registered.ref!r}"
            )


def _index_unique(items: Iterable[T], *, kind: str) -> dict[str, T]:
    result: dict[str, T] = {}
    for item in items:
        item_id = str(getattr(item, "id"))
        if item_id in result:
            raise ValueError(f"Duplicate {kind} capability id: {item_id!r}")
        result[item_id] = item
    return result


def _get(items: dict[str, T], item_id: str, *, kind: str) -> T:
    try:
        return items[item_id]
    except KeyError as exc:
        raise KeyError(f"Unknown {kind} capability: {item_id}") from exc


__all__ = [
    "CapabilityBundle",
    "CapabilityCatalog",
    "MaterializationFormat",
    "MaterializationPurpose",
    "MaterializerMetadata",
    "ModelContractRef",
    "PredictorMetadata",
    "TrainerMetadata",
    "ViewContractRef",
    "ViewDefinition",
]
