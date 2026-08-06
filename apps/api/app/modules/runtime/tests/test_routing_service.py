from __future__ import annotations

from typing import cast

import pytest

from app.modules.runtime.app.services.deployment_seed import (
    PREDICTION_RUNTIME_DEPLOYMENT,
    TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT,
    TRAIN_RUNTIME_DEPLOYMENT,
    prefect_work_pool_names,
    runtime_prefect_deployment_specs,
)
from app.modules.runtime.domain.events import (
    ArtifactProduced,
    MetricsReported,
    OperationCompleted,
    ProgressReported,
    RuntimeIssueReported,
    collect_runtime_events,
)
from app.shared.api.schemas import ArtifactRef


def test_runtime_deployments_are_declared_directly() -> None:
    assert runtime_prefect_deployment_specs() == [
        {
            "deployment_name": "train-job-deployment",
            "flow_name": "training-train-job",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.modules.training.flows.train_job:train_job_flow",
            "path": "",
        },
        {
            "deployment_name": "train-and-predict-deployment",
            "flow_name": "training-train-and-predict",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.workflows.train_predict:train_and_predict_flow",
            "path": "",
        },
        {
            "deployment_name": "predict-job-batch-deployment",
            "flow_name": "prediction-predict-job",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.modules.prediction.flows.predict_job:predict_job_flow",
            "path": "",
        },
    ]
    assert TRAIN_RUNTIME_DEPLOYMENT.work_pool_name == "default-gpu"
    assert TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT.work_pool_name == "default-gpu"
    assert PREDICTION_RUNTIME_DEPLOYMENT.work_pool_name == "default-gpu"
    assert prefect_work_pool_names() == {"default-cpu", "default-gpu"}


@pytest.mark.asyncio
async def test_runtime_event_collector_builds_terminal_payload() -> None:
    async def events():
        yield ArtifactProduced(
            ArtifactRef(id="artifact-1", uri="memory://model", kind="model")
        )
        yield MetricsReported({"loss": 0.25})
        yield ProgressReported(current=1, total=1, message="done")
        yield RuntimeIssueReported("sample_skipped", "one sample was skipped")
        yield OperationCompleted({"status": "completed"})

    result = await collect_runtime_events(events())

    assert result["status"] == "completed"
    assert result["metrics"] == {"loss": 0.25}
    artifacts = cast(list[dict[str, object]], result["artifacts"])
    issues = cast(list[dict[str, object]], result["issues"])
    assert artifacts[0]["id"] == "artifact-1"
    assert issues[0]["code"] == "sample_skipped"


@pytest.mark.asyncio
async def test_runtime_event_collector_requires_one_terminal_event() -> None:
    async def no_completion():
        yield ProgressReported(current=1)

    with pytest.raises(RuntimeError, match="without OperationCompleted"):
        await collect_runtime_events(no_completion())

    async def event_after_completion():
        yield OperationCompleted()
        yield ProgressReported(current=2)

    with pytest.raises(RuntimeError, match="after completion"):
        await collect_runtime_events(event_after_completion())
