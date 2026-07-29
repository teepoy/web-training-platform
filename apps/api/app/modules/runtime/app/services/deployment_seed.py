from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from omegaconf import OmegaConf
from pydantic import BaseModel

from app.modules.runtime.domain.routing import RuntimeDeploymentRoute


_RUNTIME_FLOW_SPECS: dict[str, dict[str, str]] = {
    "training_routes": {
        "flow_name": "training-train-job",
        "entrypoint": "app.modules.training.flows.train_job:train_job_flow",
    },
    "train_and_predict_routes": {
        "flow_name": "training-train-and-predict",
        "entrypoint": "app.workflows.train_predict:train_and_predict_flow",
    },
    "prediction_routes": {
        "flow_name": "prediction-predict-job",
        "entrypoint": "app.modules.prediction.flows.predict_job:predict_job_flow",
    },
}


def runtime_prefect_deployment_specs(config: Any) -> list[dict[str, str]]:
    routing = _get_config_value(config, "runtime_routing")
    if routing is None:
        raise RuntimeError("Missing required config: runtime_routing")

    specs_by_name: dict[str, dict[str, str]] = {}
    for section, flow_spec in _RUNTIME_FLOW_SPECS.items():
        entries = _get_config_value(routing, section)
        if entries is None:
            raise RuntimeError(f"Missing required config: runtime_routing.{section}")
        entries_raw = _to_mapping(entries, section=section)

        for catalog_id, raw_route in entries_raw.items():
            route = RuntimeDeploymentRoute.from_mapping(
                str(catalog_id),
                _to_mapping(raw_route, section=section),
                section=section,
            )
            if route.owner == "external":
                continue
            candidate = {
                "deployment_name": route.deployment,
                "flow_name": flow_spec["flow_name"],
                "work_pool_name": f"default-{route.resource_profile}",
                "entrypoint": flow_spec["entrypoint"],
                "path": "",
            }
            existing = specs_by_name.get(route.deployment)
            if existing is not None and existing != candidate:
                raise RuntimeError(
                    f"Local deployment {route.deployment!r} is assigned to "
                    "incompatible flow entrypoints"
                )
            specs_by_name[route.deployment] = candidate

    return list(specs_by_name.values())


def _get_config_value(config: Any, key: str) -> Any:
    if OmegaConf.is_config(config):
        return config.get(key)
    if isinstance(config, Mapping):
        return config.get(key)
    if hasattr(config, "get"):
        return config.get(key)
    return getattr(config, key, None)


def _to_mapping(raw: Any, *, section: str) -> dict[str, Any]:
    if OmegaConf.is_config(raw):
        raw = OmegaConf.to_container(raw, resolve=True)
    elif isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="python")
    elif hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="python")

    if not isinstance(raw, Mapping):
        raise RuntimeError(f"runtime_routing.{section} must be a mapping")
    return dict(raw)
