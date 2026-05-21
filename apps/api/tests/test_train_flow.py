"""Tests for the worker-side training flow (train_job / _run_train_job).

These tests call the training flow functions directly as plain Python — no
Prefect server required.  They exercise the full GPU-worker delegation path:
submission, status polling, artifact relay, and error handling.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.main import services as app_services
from app.shared.infrastructure.workers.gpu_worker import GpuWorkerUnavailableError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_gpu_worker(*, submit_response=None, status_sequence=None):
    """Create a mock GpuWorkerClient with controlled responses.

    ``submit_response`` — dict returned by ``submit_train``.
    ``status_sequence`` — list of dicts returned by successive
    ``get_train_status`` calls.
    """
    mock_gpu = MagicMock()
    mock_gpu.submit_train = AsyncMock(
        return_value=submit_response or {"job_id": "gpu-test-1", "status": "accepted"}
    )
    if status_sequence:
        mock_gpu.get_train_status = AsyncMock(side_effect=status_sequence)
    else:
        mock_gpu.get_train_status = AsyncMock(
            return_value={
                "job_id": "gpu-test-1",
                "status": "completed",
                "artifacts": [{"uri": "memory://models/test/model.pt", "kind": "model", "metadata": {"accuracy": 0.95}}],
                "metrics": {"accuracy": 0.95},
            }
        )
    return mock_gpu


def _install_gpu_mock(mock_gpu):
    """Override the GPU worker provider in the app services."""
    app_services.gpu_worker.override(lambda: mock_gpu)


def _remove_gpu_mock():
    """Reset the GPU worker provider override."""
    try:
        app_services.gpu_worker.reset_override()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tests — successful delegation
# ---------------------------------------------------------------------------


def test_run_train_job_delegates_to_gpu_worker() -> None:
    """Flow submits training to GPU worker and polls for completion."""
    mock_gpu = _mock_gpu_worker()
    _install_gpu_mock(mock_gpu)

    try:
        from app.modules.training.infrastructure.flows.train_job import _run_train_job

        logger = logging.getLogger("test")
        result = asyncio.run(
            _run_train_job(
                job_id="platform-job-1",
                dataset_id="ds-1",
                preset_id="resnet50-cls-v1",
                created_by="test",
                logger=logger,
            )
        )
    finally:
        _remove_gpu_mock()

    assert result["status"] == "completed"
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["kind"] == "model"

    mock_gpu.submit_train.assert_awaited_once()
    call_kwargs = mock_gpu.submit_train.call_args.kwargs
    assert call_kwargs["platform_job_id"] == "platform-job-1"
    assert call_kwargs["dataset_id"] == "ds-1"
    assert call_kwargs["preset_id"] == "resnet50-cls-v1"

    mock_gpu.get_train_status.assert_awaited_once()
    mock_gpu.get_train_status.assert_awaited_with("gpu-test-1")


def test_run_train_job_polls_multiple_statuses() -> None:
    """Flow polls repeatedly when GPU worker returns non-terminal statuses."""
    mock_gpu = _mock_gpu_worker(
        status_sequence=[
            {"job_id": "gpu-test-1", "status": "queued"},
            {"job_id": "gpu-test-1", "status": "running", "progress": 0.3},
            {"job_id": "gpu-test-1", "status": "running", "progress": 0.7},
            {
                "job_id": "gpu-test-1",
                "status": "completed",
                "artifacts": [{"uri": "s3://bucket/model.pt", "kind": "model", "metadata": {}}],
                "metrics": {"loss": 0.1},
            },
        ]
    )
    _install_gpu_mock(mock_gpu)

    try:
        from app.modules.training.infrastructure.flows.train_job import _run_train_job

        logger = logging.getLogger("test")
        result = asyncio.run(
            _run_train_job(
                job_id="p-2",
                dataset_id="ds-2",
                preset_id="resnet50-cls-v1",
                created_by="test",
                logger=logger,
            )
        )
    finally:
        _remove_gpu_mock()

    assert result["status"] == "completed"
    assert result["metrics"] == {"loss": 0.1}
    assert mock_gpu.get_train_status.await_count == 4


def test_run_train_job_preserves_artifact_uris() -> None:
    """Artifact URIs from GPU worker pass through to the flow return value."""
    mock_gpu = _mock_gpu_worker(
        status_sequence=[
            {
                "job_id": "gpu-test-1",
                "status": "completed",
                "artifacts": [
                    {"uri": "s3://artifacts/model.pth", "kind": "model", "metadata": {"framework": "pytorch"}},
                    {"uri": "s3://artifacts/metrics.json", "kind": "metrics", "metadata": {}},
                ],
                "metrics": {"precision": 0.88, "recall": 0.90},
            },
        ]
    )
    _install_gpu_mock(mock_gpu)

    try:
        from app.modules.training.infrastructure.flows.train_job import _run_train_job

        logger = logging.getLogger("test")
        result = asyncio.run(
            _run_train_job(
                job_id="p-3",
                dataset_id="ds-3",
                preset_id="resnet50-cls-v1",
                created_by="test",
                logger=logger,
            )
        )
    finally:
        _remove_gpu_mock()

    assert result["status"] == "completed"
    artifacts = result["artifacts"]
    assert len(artifacts) == 2
    assert artifacts[0]["uri"] == "s3://artifacts/model.pth"
    assert artifacts[0]["kind"] == "model"
    assert artifacts[1]["uri"] == "s3://artifacts/metrics.json"
    assert artifacts[1]["kind"] == "metrics"


# ---------------------------------------------------------------------------
# Tests — run_training_pipeline NOT called
# ---------------------------------------------------------------------------


def test_run_train_job_does_not_call_direct_training_pipeline() -> None:
    """The migrated flow must NOT call run_training_pipeline directly."""
    mock_gpu = _mock_gpu_worker()
    _install_gpu_mock(mock_gpu)

    try:
        with patch("app.modules.training.infrastructure.runtime.training_runner.run_training_pipeline") as mock_pipeline:
            from app.modules.training.infrastructure.flows.train_job import _run_train_job

            logger = logging.getLogger("test")
            asyncio.run(
                _run_train_job(
                    job_id="p-4",
                    dataset_id="ds-4",
                    preset_id="resnet50-cls-v1",
                    created_by="test",
                    logger=logger,
                )
            )

        mock_pipeline.assert_not_called()
    finally:
        _remove_gpu_mock()


def test_train_job_flow_does_not_import_run_training_pipeline() -> None:
    """The train_job module must not import run_training_pipeline."""
    import app.modules.training.infrastructure.flows.train_job as mod

    source = mod.__dict__
    assert "run_training_pipeline" not in source, "train_job module must not import run_training_pipeline"


# ---------------------------------------------------------------------------
# Tests — failure / unavailable
# ---------------------------------------------------------------------------


def test_run_train_job_gpu_worker_unavailable_on_submit() -> None:
    """GpuWorkerUnavailableError on submit propagates so Prefect marks job failed."""
    mock_gpu = _mock_gpu_worker()
    mock_gpu.submit_train = AsyncMock(
        side_effect=GpuWorkerUnavailableError("GPU worker unreachable")
    )
    _install_gpu_mock(mock_gpu)

    try:
        from app.modules.training.infrastructure.flows.train_job import _run_train_job

        logger = logging.getLogger("test")
        with pytest.raises(GpuWorkerUnavailableError, match="unreachable"):
            asyncio.run(
                _run_train_job(
                    job_id="p-5",
                    dataset_id="ds-5",
                    preset_id="resnet50-cls-v1",
                    created_by="test",
                    logger=logger,
                )
            )
    finally:
        _remove_gpu_mock()


def test_run_train_job_gpu_worker_unavailable_on_poll() -> None:
    """GpuWorkerUnavailableError on status poll propagates so Prefect marks job failed."""
    mock_gpu = _mock_gpu_worker(
        status_sequence=[
            {"job_id": "gpu-test-1", "status": "running"},
            GpuWorkerUnavailableError("GPU worker unreachable after retries"),
        ]
    )
    _install_gpu_mock(mock_gpu)

    try:
        from app.modules.training.infrastructure.flows.train_job import _run_train_job

        logger = logging.getLogger("test")
        with pytest.raises(GpuWorkerUnavailableError, match="unreachable"):
            asyncio.run(
                _run_train_job(
                    job_id="p-6",
                    dataset_id="ds-6",
                    preset_id="resnet50-cls-v1",
                    created_by="test",
                    logger=logger,
                )
            )
    finally:
        _remove_gpu_mock()


def test_run_train_job_gpu_training_failed() -> None:
    """GPU-side training failure raises RuntimeError so Prefect marks job failed."""
    mock_gpu = _mock_gpu_worker(
        status_sequence=[
            {"job_id": "gpu-test-1", "status": "running"},
            {"job_id": "gpu-test-1", "status": "failed", "error": "CUDA OOM"},
        ]
    )
    _install_gpu_mock(mock_gpu)

    try:
        from app.modules.training.infrastructure.flows.train_job import _run_train_job

        logger = logging.getLogger("test")
        with pytest.raises(RuntimeError, match="GPU training failed"):
            asyncio.run(
                _run_train_job(
                    job_id="p-7",
                    dataset_id="ds-7",
                    preset_id="resnet50-cls-v1",
                    created_by="test",
                    logger=logger,
                )
            )
    finally:
        _remove_gpu_mock()


def test_run_train_job_gpu_training_cancelled() -> None:
    """GPU-side cancellation raises RuntimeError so Prefect marks job cancelled/failed."""
    mock_gpu = _mock_gpu_worker(
        status_sequence=[
            {"job_id": "gpu-test-1", "status": "cancelled", "error": "User cancelled"},
        ]
    )
    _install_gpu_mock(mock_gpu)

    try:
        from app.modules.training.infrastructure.flows.train_job import _run_train_job

        logger = logging.getLogger("test")
        with pytest.raises(RuntimeError, match="GPU training cancelled"):
            asyncio.run(
                _run_train_job(
                    job_id="p-8",
                    dataset_id="ds-8",
                    preset_id="resnet50-cls-v1",
                    created_by="test",
                    logger=logger,
                )
            )
    finally:
        _remove_gpu_mock()


def test_run_train_job_polling_timeout() -> None:
    """Polling timeout raises TimeoutError so Prefect marks job failed."""
    mock_gpu = _mock_gpu_worker(
        status_sequence=[
            {"job_id": "gpu-test-1", "status": "running"},
        ]
        * 100
    )
    _install_gpu_mock(mock_gpu)

    try:
        from app.modules.training.infrastructure.flows.train_job import _run_train_job

        logger = logging.getLogger("test")
        with patch.dict("os.environ", {
            "GPU_WORKER_MAX_POLL_SECONDS": "0",
            "GPU_WORKER_POLL_INTERVAL": "1",
        }):
            with pytest.raises(TimeoutError, match="timed out"):
                asyncio.run(
                    _run_train_job(
                        job_id="p-9",
                        dataset_id="ds-9",
                        preset_id="resnet50-cls-v1",
                        created_by="test",
                        logger=logger,
                    )
                )
    finally:
        _remove_gpu_mock()


def test_run_train_job_logs_gpu_job_id() -> None:
    """The logger receives GPU job ID on submission."""
    mock_gpu = _mock_gpu_worker()
    _install_gpu_mock(mock_gpu)

    try:
        from app.modules.training.infrastructure.flows.train_job import _run_train_job

        logger = MagicMock(spec=logging.Logger)
        logger.info = MagicMock()
        logger.error = MagicMock()

        asyncio.run(
            _run_train_job(
                job_id="p-10",
                dataset_id="ds-10",
                preset_id="resnet50-cls-v1",
                created_by="test",
                logger=logger,
            )
        )

        submit_calls = [
            call for call in logger.info.call_args_list
            if call.args and "GPU job submitted" in str(call.args[0])
        ]
        assert len(submit_calls) == 1
        assert submit_calls[0].args[1] == "gpu-test-1"
        assert submit_calls[0].args[2] == "p-10"

        status_calls = [
            call for call in logger.info.call_args_list
            if call.args and "completed successfully" in str(call.args[0])
        ]
        assert len(status_calls) >= 1
    finally:
        _remove_gpu_mock()
