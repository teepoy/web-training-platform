from __future__ import annotations

from app.shared.infrastructure.prefect.deployments import (
    PREDICTION_RUNTIME_DEPLOYMENT,
    TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT,
    TRAIN_RUNTIME_DEPLOYMENT,
    PrefectDeploymentSpec,
    platform_prefect_deployment_specs,
    prefect_work_pool_names,
    required_prefect_deployment_names,
    runtime_prefect_deployment_specs,
)

__all__ = [
    "PREDICTION_RUNTIME_DEPLOYMENT",
    "PrefectDeploymentSpec",
    "TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT",
    "TRAIN_RUNTIME_DEPLOYMENT",
    "platform_prefect_deployment_specs",
    "prefect_work_pool_names",
    "required_prefect_deployment_names",
    "runtime_prefect_deployment_specs",
]
