"""Unit tests for PrefectWorkPoolEngine with mocked PrefectClient."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.domain.models import TrainingJob
from app.domain.types import JobStatus
from app.services.prefect_engine import PrefectWorkPoolEngine


class _RuntimeCfg:
    def __init__(self, queue: str | None) -> None:
        self.queue = queue


class _Preset:
    def __init__(self, queue: str | None) -> None:
        self.runtime = _RuntimeCfg(queue)


class _PresetRegistryStub:
    def __init__(self, by_id: dict[str, _Preset]) -> None:
        self._by_id = by_id

    def get_preset(self, preset_id: str):
        return self._by_id.get(preset_id)


@pytest.fixture()
def mock_client() -> AsyncMock:
    client = AsyncMock()
    client.resolve_deployment_id = AsyncMock(return_value="deploy-uuid-1")
    client.create_flow_run_from_deployment = AsyncMock(return_value={"id": "run-uuid-1"})
    client.get_flow_run = AsyncMock(
        return_value={
            "id": "run-uuid-1",
            "state": {"type": "SCHEDULED"},
            "parameters": {"job_id": "job-1"},
        }
    )
    client.get_flow_run_logs = AsyncMock(return_value=[])
    client.set_flow_run_state = AsyncMock()
    client.filter_flow_runs = AsyncMock(return_value=[])
    return client


@pytest.fixture()
def engine(mock_client: AsyncMock) -> PrefectWorkPoolEngine:
    return PrefectWorkPoolEngine(
        prefect_client=mock_client,
        work_pool_name="test-pool",
        work_pool_type="process",
        flow_name="train-job",
        deployment_name="train-job-deployment",
        concurrency_limit=1,
    )


@pytest.fixture()
def sample_job() -> TrainingJob:
    return TrainingJob(
        id="job-1",
        dataset_id="ds-1",
        preset_id="preset-1",
        created_by="tester",
    )


@pytest.mark.asyncio
async def test_submit(engine: PrefectWorkPoolEngine, mock_client: AsyncMock, sample_job: TrainingJob) -> None:
    result = await engine.submit(sample_job)

    assert result == "run-uuid-1"
    mock_client.resolve_deployment_id.assert_awaited_once_with("train-job-deployment")
    mock_client.create_flow_run_from_deployment.assert_awaited_once()
    call_kwargs = mock_client.create_flow_run_from_deployment.call_args
    assert call_kwargs.kwargs["deployment_id"] == "deploy-uuid-1"
    assert call_kwargs.kwargs["parameters"]["job_id"] == "job-1"


@pytest.mark.asyncio
async def test_submit_deployment_cached(engine: PrefectWorkPoolEngine, mock_client: AsyncMock, sample_job: TrainingJob) -> None:
    mock_client.create_flow_run_from_deployment.side_effect = [
        {"id": "run-1"},
        {"id": "run-2"},
    ]
    await engine.submit(sample_job)
    await engine.submit(sample_job)
    assert mock_client.resolve_deployment_id.await_count == 1


@pytest.mark.asyncio
async def test_submit_routes_dspy_queue(mock_client: AsyncMock, sample_job: TrainingJob) -> None:
    sample_job.preset_id = "dspy-vqa-v1"
    registry = _PresetRegistryStub({"dspy-vqa-v1": _Preset("optimize-llm-cpu")})
    local_engine = PrefectWorkPoolEngine(
        prefect_client=mock_client,
        work_pool_name="test-pool",
        work_pool_type="process",
        flow_name="train-job",
        deployment_name="train-job-deployment",
        preset_registry=registry,
    )

    await local_engine.submit(sample_job)
    mock_client.resolve_deployment_id.assert_awaited_once_with("train-job-dspy-deployment")


@pytest.mark.asyncio
async def test_submit_routes_default_when_no_queue(mock_client: AsyncMock, sample_job: TrainingJob) -> None:
    registry = _PresetRegistryStub({"preset-1": _Preset(None)})
    local_engine = PrefectWorkPoolEngine(
        prefect_client=mock_client,
        work_pool_name="test-pool",
        work_pool_type="process",
        flow_name="train-job",
        deployment_name="train-job-deployment",
        preset_registry=registry,
    )

    await local_engine.submit(sample_job)
    mock_client.resolve_deployment_id.assert_awaited_once_with("train-job-deployment")


@pytest.mark.asyncio
async def test_submit_deployment_not_found(mock_client: AsyncMock, sample_job: TrainingJob) -> None:
    mock_client.resolve_deployment_id.return_value = None
    local_engine = PrefectWorkPoolEngine(
        prefect_client=mock_client,
        work_pool_name="test-pool",
        work_pool_type="process",
        flow_name="train-job",
        deployment_name="missing-deployment",
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await local_engine.submit(sample_job)

    assert exc_info.value.status_code == 503
    assert "missing-deployment" in exc_info.value.detail


@pytest.mark.asyncio
async def test_status_mapping(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    test_cases = [
        ("SCHEDULED", JobStatus.QUEUED),
        ("PENDING", JobStatus.QUEUED),
        ("RUNNING", JobStatus.RUNNING),
        ("CANCELLING", JobStatus.RUNNING),
        ("COMPLETED", JobStatus.COMPLETED),
        ("FAILED", JobStatus.FAILED),
        ("CRASHED", JobStatus.FAILED),
        ("CANCELLED", JobStatus.CANCELLED),
    ]
    for prefect_state, expected_status in test_cases:
        mock_client.get_flow_run.return_value = {"id": "run-uuid-1", "state": {"type": prefect_state}}
        result = await engine.status("run-uuid-1")
        assert result == expected_status


@pytest.mark.asyncio
async def test_status_unknown_state(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    mock_client.get_flow_run.return_value = {"id": "run-uuid-1", "state": {"type": "SOME_FUTURE_STATE"}}
    result = await engine.status("run-uuid-1")
    assert result == JobStatus.QUEUED


@pytest.mark.asyncio
async def test_cancel_success(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    result = await engine.cancel("run-uuid-1")
    assert result is True
    mock_client.set_flow_run_state.assert_awaited_once_with("run-uuid-1", "CANCELLING")


@pytest.mark.asyncio
async def test_cancel_failure(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    mock_client.set_flow_run_state.side_effect = Exception("connection refused")
    result = await engine.cancel("run-uuid-1")
    assert result is False


@pytest.mark.asyncio
async def test_collect_artifacts_empty_when_missing(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    mock_client.get_flow_run.return_value = {
        "id": "run-uuid-1",
        "state": {"type": "COMPLETED", "data": {}},
    }
    artifacts = await engine.collect_artifacts("run-uuid-1")
    assert artifacts == []


@pytest.mark.asyncio
async def test_collect_artifacts_from_state(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    mock_client.get_flow_run.return_value = {
        "id": "run-uuid-1",
        "state": {
            "type": "COMPLETED",
            "data": {
                "artifacts": [
                    {"uri": "s3://bucket/model.pt", "kind": "model"},
                    {"uri": "s3://bucket/metrics.json", "kind": "metrics"},
                ]
            },
        },
    }
    artifacts = await engine.collect_artifacts("run-uuid-1")
    assert len(artifacts) == 2
    assert artifacts[0].uri == "s3://bucket/model.pt"


@pytest.mark.asyncio
async def test_stream_events_terminal(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    call_count = 0

    async def mock_get_flow_run(run_id: str) -> dict:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return {
                "id": run_id,
                "state": {"type": "RUNNING"},
                "parameters": {"job_id": "job-1"},
            }
        return {
            "id": run_id,
            "state": {"type": "COMPLETED"},
            "parameters": {"job_id": "job-1"},
        }

    mock_client.get_flow_run = AsyncMock(side_effect=mock_get_flow_run)
    mock_client.get_flow_run_logs = AsyncMock(return_value=[])

    with patch("app.services.prefect_engine.asyncio.sleep", new_callable=AsyncMock):
        events = []
        async for event in engine.stream_events("run-uuid-1"):
            events.append(event)

    messages = [e.message for e in events]
    assert any("RUNNING" in m for m in messages)
    assert any("COMPLETED" in m for m in messages)
    assert any("training completed" in m for m in messages)
