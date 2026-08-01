from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from omegaconf import OmegaConf
from pydantic import BaseModel

from app.modules.runtime.catalog import runtime_capabilities
from app.modules.runtime.domain.executables import (
    RuntimeCapabilityCatalog,
    RuntimeOperation,
)
from app.modules.runtime.domain.routing import RuntimeDeploymentRoute
from app.modules.types import catalog

_OVERRIDABLE_ROUTE_FIELDS = frozenset(
    {"deployment", "resource_profile", "owner", "code_version"}
)


class ConfigRuntimeRoutingService:
    """Resolve module-owned routes with optional environment overrides."""

    def __init__(
        self,
        config: Any,
        *,
        capability_catalog: RuntimeCapabilityCatalog = runtime_capabilities,
    ) -> None:
        self._routing = _get_config_value(config, "runtime_routing") or {}
        self._capabilities = capability_catalog

    def training_route(self, trainer_id: str) -> RuntimeDeploymentRoute:
        return self._route(RuntimeOperation.TRAIN, trainer_id)

    def prediction_route(self, predictor_id: str) -> RuntimeDeploymentRoute:
        return self._route(RuntimeOperation.PREDICT, predictor_id)

    def train_and_predict_route(self, trainer_id: str) -> RuntimeDeploymentRoute:
        return self._route(RuntimeOperation.TRAIN_AND_PREDICT, trainer_id)

    def materialization_route(
        self,
        materializer_id: str,
    ) -> RuntimeDeploymentRoute:
        raise KeyError(
            f"No module-owned materialization runtime route for {materializer_id!r}"
        )

    def validate_catalog_routes(self) -> None:
        errors: list[str] = []
        for catalog_id, definition in self._capabilities.list_routes():
            try:
                self._route(definition.operation, catalog_id)
            except (KeyError, RuntimeError) as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError("Invalid runtime catalog routing: " + "; ".join(errors))

    def _route(
        self,
        operation: RuntimeOperation,
        catalog_id: str,
    ) -> RuntimeDeploymentRoute:
        executable = self._capabilities.executable(catalog_id)
        definition = self._capabilities.route(operation, catalog_id)
        if operation is RuntimeOperation.PREDICT:
            metadata = catalog.get_predictor_meta(catalog_id)
            input_contract = metadata.input_view.contract
        else:
            metadata = catalog.get_trainer_meta(catalog_id)
            input_contract = metadata.input_view.contract

        output_contract = definition.output_contract
        if output_contract == "trainer_model":
            trainer = catalog.get_trainer_meta(catalog_id)
            output_contract = trainer.output_model.contract

        raw: dict[str, Any] = {
            "deployment": definition.deployment,
            "input_contract": input_contract,
            "output_contract": output_contract,
            "resource_profile": definition.resource_profile,
            "owner": definition.owner,
            "algo_id": executable.algo_id,
            "algo_version": executable.algo_version,
            "missing_image_policy": definition.missing_image_policy,
        }
        override = self._override(operation.value, catalog_id)
        unexpected = set(override) - _OVERRIDABLE_ROUTE_FIELDS
        if unexpected:
            raise RuntimeError(
                f"runtime_routing.{operation.value}.{catalog_id} may override only "
                f"{sorted(_OVERRIDABLE_ROUTE_FIELDS)}; got {sorted(unexpected)}"
            )
        raw.update({key: value for key, value in override.items() if value is not None})
        return RuntimeDeploymentRoute.from_mapping(
            catalog_id,
            raw,
            section=operation.value,
        )

    def _override(self, section: str, catalog_id: str) -> dict[str, Any]:
        entries = _get_config_value(self._routing, section)
        if entries is None:
            return {}
        raw = _get_config_value(entries, catalog_id)
        if raw is None:
            return {}
        return _to_mapping(raw)


def _get_config_value(config: Any, key: str) -> Any:
    if OmegaConf.is_config(config):
        return config.get(key)
    if isinstance(config, Mapping):
        return config.get(key)
    if hasattr(config, "get"):
        return config.get(key)
    return getattr(config, key, None)


def _to_mapping(raw: Any) -> dict[str, Any]:
    if OmegaConf.is_config(raw):
        raw = OmegaConf.to_container(raw, resolve=True)
    elif isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="python", exclude_none=True)
    elif hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="python", exclude_none=True)
    if not isinstance(raw, Mapping):
        raise RuntimeError("Runtime deployment override must be a mapping")
    return dict(raw)
