from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from omegaconf import OmegaConf
from pydantic import BaseModel

from app.modules.runtime.domain.routing import RuntimeDeploymentRoute
from app.modules.types import catalog


class ConfigRuntimeRoutingService:
    def __init__(self, config: Any) -> None:
        self._routing = _get_config_value(config, "runtime_routing")
        if self._routing is None:
            raise RuntimeError("Missing required config: runtime_routing")

    def training_route(self, trainer_id: str) -> RuntimeDeploymentRoute:
        return self._route("training_routes", trainer_id)

    def prediction_route(
        self,
        predictor_id: str,
    ) -> RuntimeDeploymentRoute:
        return self._route("prediction_routes", predictor_id)

    def train_and_predict_route(
        self,
        trainer_id: str,
    ) -> RuntimeDeploymentRoute:
        return self._route("train_and_predict_routes", trainer_id)

    def materialization_route(
        self,
        materializer_id: str,
    ) -> RuntimeDeploymentRoute:
        return self._route("materialization_routes", materializer_id)

    def validate_catalog_routes(self) -> None:
        """Verify that product catalog entries have compatible environment routes."""

        errors: list[str] = []
        for trainer in catalog.list_trainers():
            try:
                train_route = self.training_route(trainer.id)
                workflow_route = self.train_and_predict_route(trainer.id)
                for predictor_id in trainer.predictor_ids:
                    catalog.get_predictor_meta(predictor_id)
            except (KeyError, RuntimeError) as exc:
                errors.append(str(exc))
                continue
            if train_route.input_contract != trainer.input_view.contract:
                errors.append(
                    f"training_routes.{trainer.id}.input_contract="
                    f"{train_route.input_contract!r} does not match catalog "
                    f"view contract={trainer.input_view.contract!r}"
                )
            if train_route.output_contract != trainer.output_model.contract:
                errors.append(
                    f"training_routes.{trainer.id}.output_contract="
                    f"{train_route.output_contract!r} does not match catalog "
                    f"model contract={trainer.output_model.contract!r}"
                )
            if workflow_route.input_contract != trainer.input_view.contract:
                errors.append(
                    f"train_and_predict_routes.{trainer.id}.input_contract="
                    f"{workflow_route.input_contract!r} does not match catalog "
                    f"view contract={trainer.input_view.contract!r}"
                )
            if catalog.get_view_meta(trainer.view_id).image_roles:
                _require_missing_image_policy(
                    errors,
                    train_route,
                    section="training_routes",
                )
                _require_missing_image_policy(
                    errors,
                    workflow_route,
                    section="train_and_predict_routes",
                )
        for predictor in catalog.list_predictors():
            try:
                route = self.prediction_route(predictor.id)
            except RuntimeError as exc:
                errors.append(str(exc))
                continue
            if route.input_contract != predictor.input_view.contract:
                errors.append(
                    f"prediction_routes.{predictor.id}.input_contract="
                    f"{route.input_contract!r} does not match catalog "
                    f"view contract={predictor.input_view.contract!r}"
                )
            if catalog.get_view_meta(predictor.view_id).image_roles:
                _require_missing_image_policy(
                    errors,
                    route,
                    section="prediction_routes",
                )

        if errors:
            raise RuntimeError("Invalid runtime catalog routing: " + "; ".join(errors))

    def _route(self, section: str, catalog_id: str) -> RuntimeDeploymentRoute:
        entries = _get_config_value(self._routing, section)
        if entries is None:
            raise RuntimeError(f"Missing required config: runtime_routing.{section}")
        raw = _get_config_value(entries, catalog_id)
        if raw is None:
            raise RuntimeError(
                f"No runtime deployment route for runtime_routing.{section}.{catalog_id}"
            )
        return RuntimeDeploymentRoute.from_mapping(
            catalog_id,
            _to_route_mapping(raw),
            section=section,
        )


def _require_missing_image_policy(
    errors: list[str],
    route: RuntimeDeploymentRoute,
    *,
    section: str,
) -> None:
    if route.missing_image_policy is None:
        errors.append(
            f"{section}.{route.catalog_id}.missing_image_policy must be explicit "
            "for an image-bearing view"
        )


def _get_config_value(config: Any, key: str) -> Any:
    if OmegaConf.is_config(config):
        return config.get(key)
    if isinstance(config, Mapping):
        return config.get(key)
    if hasattr(config, "get"):
        return config.get(key)
    return getattr(config, key, None)


def _to_route_mapping(raw: Any) -> dict[str, Any]:
    if OmegaConf.is_config(raw):
        raw = OmegaConf.to_container(raw, resolve=True)
    elif isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="python")
    elif hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="python")

    if not isinstance(raw, Mapping):
        raise RuntimeError("Runtime deployment route must be a mapping")
    return dict(raw)
