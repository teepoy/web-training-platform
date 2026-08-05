from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeVar

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
    """Module-owned data/view declarations consumed by the type catalog."""

    views: tuple[ViewDefinition, ...] = ()


class CapabilityCatalog:
    """Immutable-by-construction aggregate of module capability bundles."""

    def __init__(self, bundles: tuple[CapabilityBundle, ...]) -> None:
        self._views = _index_unique(
            (view for bundle in bundles for view in bundle.views),
            kind="view",
        )
        self._validate_relationships()

    def list_views(self) -> tuple[ViewDefinition, ...]:
        return tuple(self._views.values())

    def get_view(self, view_id: str) -> ViewDefinition:
        return _get(self._views, view_id, kind="view")

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
    "ModelContractRef",
    "PredictorMetadata",
    "TrainerMetadata",
    "ViewContractRef",
    "ViewDefinition",
]
