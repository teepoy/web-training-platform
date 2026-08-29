from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PrefectDeploymentSpec:
    deployment_name: str
    flow_name: str
    work_pool_name: str
    entrypoint: str
    path: str = ""
    work_queue_name: str | None = None
    work_queue_priority: int | None = None
    cron: str | None = None
    cron_timezone: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "deployment_name": self.deployment_name,
            "flow_name": self.flow_name,
            "work_pool_name": self.work_pool_name,
            "entrypoint": self.entrypoint,
            "path": self.path,
        }
        if self.work_queue_name is not None:
            result["work_queue_name"] = self.work_queue_name
        if self.work_queue_priority is not None:
            result["work_queue_priority"] = self.work_queue_priority
        if self.cron is not None:
            if self.cron_timezone is None:
                raise ValueError("cron_timezone is required when cron is configured")
            result["schedules"] = [
                {
                    "schedule": {
                        "cron": self.cron,
                        "timezone": self.cron_timezone,
                    },
                    "active": True,
                }
            ]
        return result


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
    work_queue_name="prediction-manual",
    work_queue_priority=1,
)
PREDICTION_AUTOMATION_RUNTIME_DEPLOYMENT = PrefectDeploymentSpec(
    deployment_name="predict-job-batch-automation-deployment",
    flow_name="prediction-predict-job",
    work_pool_name="default-gpu",
    entrypoint="app.modules.prediction.flows.predict_job:predict_job_flow",
    work_queue_name="prediction-automation",
    work_queue_priority=10,
)
COLLECTION_DISCOVERY_DEPLOYMENT = PrefectDeploymentSpec(
    deployment_name="collection-discovery-poll",
    flow_name="collection-discovery-poll",
    work_pool_name="default-cpu",
    entrypoint=(
        "app.modules.source_discovery.adapter.flows.collection_discovery:"
        "collection_discovery_poll"
    ),
    cron="*/5 * * * *",
    cron_timezone="UTC",
)
CONTROL_PLANE_WORK_POOL_NAME = COLLECTION_DISCOVERY_DEPLOYMENT.work_pool_name
DRAIN_DATASET_DEPLOYMENT = PrefectDeploymentSpec(
    deployment_name="drain-dataset",
    flow_name="drain-dataset",
    work_pool_name="default-cpu",
    entrypoint="app.modules.datasets.adapter.flows.drain_dataset:drain_dataset",
)

_RUNTIME_DEPLOYMENTS = (
    TRAIN_RUNTIME_DEPLOYMENT,
    TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT,
    PREDICTION_RUNTIME_DEPLOYMENT,
    PREDICTION_AUTOMATION_RUNTIME_DEPLOYMENT,
)
_CPU_DEPLOYMENTS = (
    COLLECTION_DISCOVERY_DEPLOYMENT,
    DRAIN_DATASET_DEPLOYMENT,
)
_PLATFORM_DEPLOYMENTS = (*_RUNTIME_DEPLOYMENTS, *_CPU_DEPLOYMENTS)

# Scheduling is an explicit product capability. Do not infer it from work-pool
# type or expose every repository-owned deployment automatically.
_SCHEDULABLE_DEPLOYMENTS = (DRAIN_DATASET_DEPLOYMENT,)


def runtime_prefect_deployment_specs() -> list[dict[str, object]]:
    return [spec.as_dict() for spec in _RUNTIME_DEPLOYMENTS]


def platform_prefect_deployment_specs() -> list[dict[str, object]]:
    """Return every repository-owned Prefect deployment."""

    return [spec.as_dict() for spec in _PLATFORM_DEPLOYMENTS]


def schedulable_prefect_deployment_specs() -> tuple[PrefectDeploymentSpec, ...]:
    """Return deployment descriptors that users may bind cron schedules to."""

    return _SCHEDULABLE_DEPLOYMENTS


def get_schedulable_prefect_deployment(
    flow_name: str,
) -> PrefectDeploymentSpec | None:
    return next(
        (spec for spec in _SCHEDULABLE_DEPLOYMENTS if spec.flow_name == flow_name),
        None,
    )


def required_prefect_deployment_names() -> set[str]:
    return {spec.deployment_name for spec in _PLATFORM_DEPLOYMENTS}


def prefect_work_pool_names() -> set[str]:
    return {spec.work_pool_name for spec in _PLATFORM_DEPLOYMENTS}


def prefect_work_queue_specs() -> tuple[tuple[str, str, int], ...]:
    """Return repository-owned queues as pool/name/priority tuples."""

    return tuple(
        (spec.work_pool_name, spec.work_queue_name, spec.work_queue_priority)
        for spec in _PLATFORM_DEPLOYMENTS
        if spec.work_queue_name is not None and spec.work_queue_priority is not None
    )


__all__ = [
    "COLLECTION_DISCOVERY_DEPLOYMENT",
    "CONTROL_PLANE_WORK_POOL_NAME",
    "DRAIN_DATASET_DEPLOYMENT",
    "PREDICTION_AUTOMATION_RUNTIME_DEPLOYMENT",
    "PREDICTION_RUNTIME_DEPLOYMENT",
    "PrefectDeploymentSpec",
    "TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT",
    "TRAIN_RUNTIME_DEPLOYMENT",
    "get_schedulable_prefect_deployment",
    "platform_prefect_deployment_specs",
    "prefect_work_pool_names",
    "prefect_work_queue_specs",
    "required_prefect_deployment_names",
    "runtime_prefect_deployment_specs",
    "schedulable_prefect_deployment_specs",
]
