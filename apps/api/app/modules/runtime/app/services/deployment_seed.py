from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PrefectDeploymentSpec:
    deployment_name: str
    flow_name: str
    work_pool_name: str
    entrypoint: str
    path: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "deployment_name": self.deployment_name,
            "flow_name": self.flow_name,
            "work_pool_name": self.work_pool_name,
            "entrypoint": self.entrypoint,
            "path": self.path,
        }


TRAIN_RUNTIME_DEPLOYMENT = PrefectDeploymentSpec(
    deployment_name="train-job-deployment",
    flow_name="training-train-job",
    work_pool_name="default-gpu",
    entrypoint="app.modules.training.flows.train_job:train_job_flow",
)
TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT = PrefectDeploymentSpec(
    deployment_name="train-and-predict-deployment",
    flow_name="training-train-and-predict",
    work_pool_name="default-gpu",
    entrypoint="app.workflows.train_predict:train_and_predict_flow",
)
PREDICTION_RUNTIME_DEPLOYMENT = PrefectDeploymentSpec(
    deployment_name="predict-job-batch-deployment",
    flow_name="prediction-predict-job",
    work_pool_name="default-gpu",
    entrypoint="app.modules.prediction.flows.predict_job:predict_job_flow",
)

_RUNTIME_DEPLOYMENTS = (
    TRAIN_RUNTIME_DEPLOYMENT,
    TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT,
    PREDICTION_RUNTIME_DEPLOYMENT,
)
_CPU_DEPLOYMENTS = (
    PrefectDeploymentSpec(
        deployment_name="timer-sensor",
        flow_name="timer-sensor",
        work_pool_name="default-cpu",
        entrypoint="app.modules.jobs.sensors.adapter.flows.timer_sensor:timer_sensor",
    ),
    PrefectDeploymentSpec(
        deployment_name="dataset-size-sensor",
        flow_name="dataset-size-sensor",
        work_pool_name="default-cpu",
        entrypoint=(
            "app.modules.jobs.sensors.adapter.flows.dataset_size_sensor:"
            "dataset_size_sensor"
        ),
    ),
    PrefectDeploymentSpec(
        deployment_name="drain-dataset",
        flow_name="drain-dataset",
        work_pool_name="default-cpu",
        entrypoint="app.modules.datasets.adapter.flows.drain_dataset:drain_dataset",
    ),
)
_PLATFORM_DEPLOYMENTS = (*_RUNTIME_DEPLOYMENTS, *_CPU_DEPLOYMENTS)


def runtime_prefect_deployment_specs() -> list[dict[str, str]]:
    return [spec.as_dict() for spec in _RUNTIME_DEPLOYMENTS]


def platform_prefect_deployment_specs() -> list[dict[str, str]]:
    """Return every repository-owned Prefect deployment."""

    return [spec.as_dict() for spec in _PLATFORM_DEPLOYMENTS]


def required_prefect_deployment_names() -> set[str]:
    return {spec.deployment_name for spec in _PLATFORM_DEPLOYMENTS}


def prefect_work_pool_names() -> set[str]:
    return {spec.work_pool_name for spec in _PLATFORM_DEPLOYMENTS}


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
