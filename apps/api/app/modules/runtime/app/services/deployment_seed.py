from __future__ import annotations

from typing import Any

from app.modules.runtime.app.services.routing_service import (
    ConfigRuntimeRoutingService,
)
from app.modules.runtime.catalog import runtime_catalog
from app.modules.runtime.domain.executables import RuntimeOperation
from app.modules.runtime.domain.routing import RuntimeDeploymentRoute

_RUNTIME_FLOW_SPECS: dict[RuntimeOperation, dict[str, str]] = {
    RuntimeOperation.TRAIN: {
        "flow_name": "training-train-job",
        "entrypoint": "app.modules.training.flows.train_job:train_job_flow",
    },
    RuntimeOperation.TRAIN_AND_PREDICT: {
        "flow_name": "training-train-and-predict",
        "entrypoint": "app.workflows.train_predict:train_and_predict_flow",
    },
    RuntimeOperation.PREDICT: {
        "flow_name": "prediction-predict-job",
        "entrypoint": "app.modules.prediction.flows.predict_job:predict_job_flow",
    },
}

_CPU_DEPLOYMENT_SPECS: tuple[dict[str, str], ...] = (
    {
        "deployment_name": "timer-sensor",
        "flow_name": "timer-sensor",
        "work_pool_name": "default-cpu",
        "entrypoint": "app.modules.jobs.sensors.adapter.flows.timer_sensor:timer_sensor",
        "path": "",
    },
    {
        "deployment_name": "dataset-size-sensor",
        "flow_name": "dataset-size-sensor",
        "work_pool_name": "default-cpu",
        "entrypoint": "app.modules.jobs.sensors.adapter.flows.dataset_size_sensor:dataset_size_sensor",
        "path": "",
    },
    {
        "deployment_name": "drain-dataset",
        "flow_name": "drain-dataset",
        "work_pool_name": "default-cpu",
        "entrypoint": "app.modules.datasets.adapter.flows.drain_dataset:drain_dataset",
        "path": "",
    },
)


def runtime_prefect_deployment_specs(config: Any) -> list[dict[str, str]]:
    routing = ConfigRuntimeRoutingService(config)
    specs_by_name: dict[str, dict[str, str]] = {}
    for catalog_id, definition in runtime_catalog.list_routes():
        route = _resolve_route(routing, definition.operation, catalog_id)
        if route.owner == "external":
            continue
        flow_spec = _RUNTIME_FLOW_SPECS[definition.operation]
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


def platform_prefect_deployment_specs(config: Any) -> list[dict[str, str]]:
    """Return every API-owned Prefect deployment from one declaration source."""
    return [*runtime_prefect_deployment_specs(config), *_CPU_DEPLOYMENT_SPECS]


def required_prefect_deployment_names(config: Any) -> set[str]:
    """Return all deployments the API must resolve, including external routes."""
    routing = ConfigRuntimeRoutingService(config)
    names = {spec["deployment_name"] for spec in _CPU_DEPLOYMENT_SPECS}
    for catalog_id, definition in runtime_catalog.list_routes():
        route = _resolve_route(routing, definition.operation, catalog_id)
        names.add(route.deployment)
    return names


def _resolve_route(
    routing: ConfigRuntimeRoutingService,
    operation: RuntimeOperation,
    catalog_id: str,
) -> RuntimeDeploymentRoute:
    if operation is RuntimeOperation.TRAIN:
        return routing.training_route(catalog_id)
    if operation is RuntimeOperation.TRAIN_AND_PREDICT:
        return routing.train_and_predict_route(catalog_id)
    return routing.prediction_route(catalog_id)
