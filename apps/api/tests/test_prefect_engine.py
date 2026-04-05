"""Unit tests for PrefectWorkPoolEngine with mocked PrefectClient.

These tests verify the engine's Protocol implementation (submit, status,
stream_events, cancel, collect_artifacts) without requiring a live Prefect
server — all PrefectClient methods are patched via AsyncMock.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.models import TrainingJob
from app.domain.types import JobStatus
from app.services.prefect_engine import PrefectWorkPoolEngine


@pytest.fixture()
def mock_client() -> AsyncMock:
    """Return a fully mocked PrefectClient with sensible defaults."""
    client = AsyncMock()
    client.ensure_work_pool = AsyncMock()
    client.resolve_flow_id = AsyncMock(return_value="flow-uuid-1")
    client.create_flow_run = AsyncMock(return_value={"id": "run-uuid-1"})
    client.get_flow_run = AsyncMock(return_value={
        "id": "run-uuid-1",
        "state": {"type": "SCHEDULED"},
        "parameters": {"job_id": "job-1"},
    })
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
    """submit() ensures pool, resolves flow, creates run, returns run ID."""
    result = await engine.submit(sample_job)

    assert result == "run-uuid-1"
    mock_client.ensure_work_pool.assert_awaited_once_with("test-pool", "process", 1)
    mock_client.resolve_flow_id.assert_awaited_once_with("train-job")
    mock_client.create_flow_run.assert_awaited_once()
    # Verify parameters passed
    call_kwargs = mock_client.create_flow_run.call_args
    assert call_kwargs.kwargs["flow_id"] == "flow-uuid-1"
    assert call_kwargs.kwargs["work_pool_name"] == "test-pool"
    assert call_kwargs.kwargs["parameters"]["job_id"] == "job-1"


@pytest.mark.asyncio
async def test_submit_pool_ensured_once(engine: PrefectWorkPoolEngine, mock_client: AsyncMock, sample_job: TrainingJob) -> None:
    """Pool should only be ensured once across multiple submits."""
    mock_client.create_flow_run.side_effect = [
        {"id": "run-1"},
        {"id": "run-2"},
    ]
    await engine.submit(sample_job)
    await engine.submit(sample_job)

    assert mock_client.ensure_work_pool.await_count == 1


@pytest.mark.asyncio
async def test_status_mapping(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    """status() correctly maps Prefect states to JobStatus."""
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
        mock_client.get_flow_run.return_value = {
            "id": "run-uuid-1",
            "state": {"type": prefect_state},
        }
        result = await engine.status("run-uuid-1")
        assert result == expected_status, f"Expected {expected_status} for {prefect_state}, got {result}"


@pytest.mark.asyncio
async def test_status_unknown_state(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    """Unknown Prefect state should default to QUEUED."""
    mock_client.get_flow_run.return_value = {
        "id": "run-uuid-1",
        "state": {"type": "SOME_FUTURE_STATE"},
    }
    result = await engine.status("run-uuid-1")
    assert result == JobStatus.QUEUED


@pytest.mark.asyncio
async def test_cancel_success(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    """cancel() returns True when set_flow_run_state succeeds."""
    result = await engine.cancel("run-uuid-1")
    assert result is True
    mock_client.set_flow_run_state.assert_awaited_once_with("run-uuid-1", "CANCELLING")


@pytest.mark.asyncio
async def test_cancel_failure(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    """cancel() returns False when set_flow_run_state raises."""
    mock_client.set_flow_run_state.side_effect = Exception("connection refused")
    result = await engine.cancel("run-uuid-1")
    assert result is False


@pytest.mark.asyncio
async def test_collect_artifacts_fallback(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    """collect_artifacts() returns placeholder artifacts when no data in run state."""
    mock_client.get_flow_run.return_value = {
        "id": "run-uuid-1",
        "state": {"type": "COMPLETED", "data": {}},
    }
    artifacts = await engine.collect_artifacts("run-uuid-1")
    assert len(artifacts) == 2
    assert artifacts[0].kind == "model"
    assert "run-uuid-1" in artifacts[0].uri
    assert artifacts[1].kind == "metrics"


@pytest.mark.asyncio
async def test_collect_artifacts_from_state(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    """collect_artifacts() extracts artifacts from state data when available."""
    mock_client.get_flow_run.return_value = {
        "id": "run-uuid-1",
        "state": {
            "type": "COMPLETED",
            "data": {
                "artifacts": [
                    {"uri": "s3://bucket/model.pt", "kind": "model"},
                    {"uri": "s3://bucket/metrics.json", "kind": "metrics"},
                ],
            },
        },
    }
    artifacts = await engine.collect_artifacts("run-uuid-1")
    assert len(artifacts) == 2
    assert artifacts[0].uri == "s3://bucket/model.pt"


@pytest.mark.asyncio
async def test_stream_events_terminal(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    """stream_events() yields state transitions and terminates on COMPLETED."""
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

    # Patch asyncio.sleep to avoid real delays
    with patch("app.services.prefect_engine.asyncio.sleep", new_callable=AsyncMock):
        events = []
        async for event in engine.stream_events("run-uuid-1"):
            events.append(event)

    # Should have: state change to RUNNING, state change to COMPLETED, final "training completed"
    messages = [e.message for e in events]
    assert any("RUNNING" in m for m in messages)
    assert any("COMPLETED" in m for m in messages)
    assert any("training completed" in m for m in messages)


@pytest.mark.asyncio
async def test_stream_events_with_logs(engine: PrefectWorkPoolEngine, mock_client: AsyncMock) -> None:
    """stream_events() yields log messages incrementally."""
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

    log_call_count = 0

    async def mock_get_logs(run_id: str) -> list[dict]:
        nonlocal log_call_count
        log_call_count += 1
        if log_call_count == 1:
            return [{"message": "Starting training", "level": 20}]
        if log_call_count == 2:
            return [
                {"message": "Starting training", "level": 20},
                {"message": "Epoch 1/3", "level": 20},
            ]
        return [
            {"message": "Starting training", "level": 20},
            {"message": "Epoch 1/3", "level": 20},
            {"message": "Training complete", "level": 20},
        ]

    mock_client.get_flow_run = AsyncMock(side_effect=mock_get_flow_run)
    mock_client.get_flow_run_logs = AsyncMock(side_effect=mock_get_logs)

    with patch("app.services.prefect_engine.asyncio.sleep", new_callable=AsyncMock):
        events = []
        async for event in engine.stream_events("run-uuid-1"):
            events.append(event)

    messages = [e.message for e in events]
    assert "Starting training" in messages
    assert "Epoch 1/3" in messages
