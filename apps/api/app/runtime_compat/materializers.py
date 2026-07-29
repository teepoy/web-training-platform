from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

from injector import Injector

from app.modules.types import catalog


@dataclass(frozen=True, slots=True)
class LocalMaterializerBinding:
    catalog_id: str
    port_path: str


_LOCAL_MATERIALIZER_BINDINGS = (
    LocalMaterializerBinding(
        catalog_id="sc-inspection-patch-image-v1",
        port_path=(
            "app.modules.sc.materialization.port.local:ScInspectionMaterializerPort"
        ),
    ),
)

_BINDINGS_BY_ID = {
    binding.catalog_id: binding for binding in _LOCAL_MATERIALIZER_BINDINGS
}


def list_local_materializer_bindings() -> tuple[LocalMaterializerBinding, ...]:
    return _LOCAL_MATERIALIZER_BINDINGS


def resolve_local_materializer(injector: Injector, materializer_id: str) -> Any:
    binding = _BINDINGS_BY_ID.get(materializer_id)
    if binding is None:
        raise KeyError(
            f"materializer_id={materializer_id!r} has no local compatibility binding"
        )
    module_name, separator, symbol_name = binding.port_path.partition(":")
    if not separator:
        raise RuntimeError(
            f"Invalid local materializer port path: {binding.port_path!r}"
        )
    port_type = getattr(import_module(module_name), symbol_name)
    return injector.get(port_type)


def validate_local_materializer_bindings() -> None:
    seen: set[str] = set()
    for binding in _LOCAL_MATERIALIZER_BINDINGS:
        if binding.catalog_id in seen:
            raise RuntimeError(
                f"Duplicate local materializer binding: {binding.catalog_id!r}"
            )
        seen.add(binding.catalog_id)
        try:
            catalog.get_materializer_meta(binding.catalog_id)
        except KeyError as exc:
            raise RuntimeError(
                f"Local materializer binding has no catalog metadata: "
                f"{binding.catalog_id!r}"
            ) from exc


validate_local_materializer_bindings()


__all__ = [
    "LocalMaterializerBinding",
    "list_local_materializer_bindings",
    "resolve_local_materializer",
    "validate_local_materializer_bindings",
]
