from __future__ import annotations

from typing import Any, cast

import pytest

from app.modules.runtime.app.services.deployment_catalog import (
    PREDICTION_AUTOMATION_RUNTIME_DEPLOYMENT,
    PREDICTION_RUNTIME_DEPLOYMENT,
    TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT,
    TRAIN_RUNTIME_DEPLOYMENT,
    prefect_work_pool_names,
    runtime_prefect_deployment_specs,
)
from app.modules.runtime.app.services.artifact_output_sink import (
    PlatformArtifactOutputSink,
)
from app.modules.runtime.domain.events import (
    ArtifactOutput,
    LocalArtifactFile,
    MetricsReported,
    OperationCompleted,
    ProgressReported,
    RuntimeIssueReported,
    StoredArtifact,
    collect_runtime_events,
)
from app.shared.api.schemas import ArtifactRef
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage


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
            "work_queue_name": "prediction-manual",
            "work_queue_priority": 1,
        },
        {
            "deployment_name": "predict-job-batch-automation-deployment",
            "flow_name": "prediction-predict-job",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.modules.prediction.flows.predict_job:predict_job_flow",
            "path": "",
            "work_queue_name": "prediction-automation",
            "work_queue_priority": 10,
        },
    ]
    assert TRAIN_RUNTIME_DEPLOYMENT.work_pool_name == "default-gpu"
    assert TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT.work_pool_name == "default-gpu"
    assert PREDICTION_RUNTIME_DEPLOYMENT.work_pool_name == "default-gpu"
    assert PREDICTION_RUNTIME_DEPLOYMENT.work_queue_priority == 1
    assert PREDICTION_AUTOMATION_RUNTIME_DEPLOYMENT.work_queue_priority == 10
    assert prefect_work_pool_names() == {"default-cpu", "default-gpu"}


@pytest.mark.asyncio
async def test_runtime_event_collector_builds_terminal_payload() -> None:
    class Sink:
        async def persist(self, output: ArtifactOutput) -> ArtifactRef:
            assert output.id == "artifact-1"
            assert isinstance(output.payload, StoredArtifact)
            return ArtifactRef(
                id=output.id,
                uri=output.payload.uri,
                kind=output.kind,
                metadata=dict(output.metadata),
            )

    async def events():
        yield ArtifactOutput(
            id="artifact-1",
            kind="model",
            payload=StoredArtifact("memory://model"),
        )
        yield MetricsReported({"loss": 0.25})
        yield ProgressReported(current=1, total=1, message="done")
        yield RuntimeIssueReported("sample_skipped", "one sample was skipped")
        yield OperationCompleted({"status": "completed"})

    result = await collect_runtime_events(events(), artifact_sink=Sink())

    assert result["status"] == "completed"
    assert result["metrics"] == {"loss": 0.25}
    artifacts = cast(list[dict[str, object]], result["artifacts"])
    issues = cast(list[dict[str, object]], result["issues"])
    assert artifacts[0]["id"] == "artifact-1"
    assert issues[0]["code"] == "sample_skipped"


@pytest.mark.asyncio
async def test_runtime_event_collector_rejects_artifact_without_sink() -> None:
    async def events():
        yield ArtifactOutput(
            id="artifact-1",
            kind="model",
            payload=StoredArtifact("memory://model"),
        )
        yield OperationCompleted()

    with pytest.raises(RuntimeError, match="without an artifact sink"):
        await collect_runtime_events(events())


@pytest.mark.asyncio
async def test_platform_artifact_sink_uploads_file_and_upserts_reference(
    tmp_path,
) -> None:
    storage = InMemoryArtifactStorage()
    persisted: list[tuple[str, list[ArtifactRef]]] = []

    class Repository:
        async def upsert_artifacts(
            self,
            job_id: str,
            artifacts: list[ArtifactRef],
        ) -> None:
            persisted.append((job_id, artifacts))

    repository = Repository()

    checkpoint_path = tmp_path / "checkpoint.pt"
    checkpoint_path.write_bytes(b"checkpoint")
    sink = PlatformArtifactOutputSink(
        storage=storage,
        repository=cast(Any, repository),
        job_id="job-1",
    )

    artifact = await sink.persist(
        ArtifactOutput(
            id="artifact-1",
            kind="model",
            payload=LocalArtifactFile(
                path=checkpoint_path,
                object_name="models/job-1/checkpoint.pt",
            ),
            metadata={"framework": "pytorch"},
        )
    )

    assert artifact.uri == "memory://models/job-1/checkpoint.pt"
    assert artifact.file_size == len(b"checkpoint")
    assert await storage.get_bytes(artifact.uri) == b"checkpoint"
    assert persisted == [("job-1", [artifact])]


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
