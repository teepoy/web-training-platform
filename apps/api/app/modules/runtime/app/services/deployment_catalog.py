from __future__ import annotations

from app.shared.infrastructure.prefect.deployments import (
    PREDICTION_AUTOMATION_RUNTIME_DEPLOYMENT,
    PREDICTION_RUNTIME_DEPLOYMENT,
    TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT,
    TRAIN_RUNTIME_DEPLOYMENT,
    PrefectDeploymentSpec,
    platform_prefect_deployment_specs,
    prefect_work_pool_names,
    prefect_work_queue_specs,
    required_prefect_deployment_names,
    runtime_prefect_deployment_specs,
)

__all__ = [
    "PREDICTION_AUTOMATION_RUNTIME_DEPLOYMENT",
    "PREDICTION_RUNTIME_DEPLOYMENT",
    "PrefectDeploymentSpec",
    "TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT",
    "TRAIN_RUNTIME_DEPLOYMENT",
    "platform_prefect_deployment_specs",
    "prefect_work_pool_names",
    "prefect_work_queue_specs",
    "required_prefect_deployment_names",
    "runtime_prefect_deployment_specs",
]
