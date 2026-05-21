"""Tests for the GPU worker HTTP client.

Covers train submit/status/cancel/logs, predict/embed compatibility methods,
and error/retry/unavailable behaviour.
"""
from __future__ import annotations

from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.shared.infrastructure.workers.gpu_worker import (
    GpuWorkerClient,
    GpuWorkerClientError,
    GpuWorkerUnavailableError,
)

BASE_URL = "http://gpu-worker:9999"


# ── Helpers ──────────────────────────────────────────────────────────


def _response(status: int, body: dict | None = None, text: str = "") -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.is_success = 200 <= status < 300
    r.text = text
    r.json = MagicMock(return_value=body or {})
    if status >= 400:
        # raise_for_status will raise HTTPStatusError
        http_error = httpx.HTTPStatusError(
            f"HTTP {status}",
            request=MagicMock(),
            response=r,
        )
        r.raise_for_status = MagicMock(side_effect=http_error)
    else:
        r.raise_for_status = MagicMock()
    return r


def _mock_http(*responses: MagicMock) -> MagicMock:
    """Create an AsyncMock for httpx.AsyncClient that returns the given responses in order.

    Pass one response for success, or multiple for retry scenarios.
    """
    client = AsyncMock()
    # Set up get/post mock methods returning responses in sequence
    if len(responses) == 1:
        client.get = AsyncMock(return_value=responses[0])
        client.post = AsyncMock(return_value=responses[0])
    else:
        client.get = AsyncMock(side_effect=list(responses))
        client.post = AsyncMock(side_effect=list(responses))

    # Make the client itself an async context manager
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ── Construction ─────────────────────────────────────────────────────


def test_client_requires_base_url() -> None:
    with pytest.raises(GpuWorkerClientError, match="not configured"):
        GpuWorkerClient(base_url="")


def test_client_accepts_default_timeout() -> None:
    client = GpuWorkerClient(base_url=BASE_URL)
    assert client._timeout_seconds == 60.0  # noqa: S105


def test_client_accepts_custom_timeout_and_retries() -> None:
    client = GpuWorkerClient(
        base_url=BASE_URL,
        timeout_seconds=10.0,
        max_retries=5,
        retry_delay_seconds=0.5,
    )
    assert client._timeout_seconds == 10.0  # noqa: S105
    assert client._max_retries == 5
    assert client._retry_delay_seconds == 0.5  # noqa: S105


# ── submit_train ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_train_success() -> None:
    expected = {"job_id": "gpu-abc", "status": "accepted", "position": 0}
    http = _mock_http(_response(202, expected))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        result = await client.submit_train(
            platform_job_id="p-1",
            preset_id="resnet50",
            dataset_id="ds-1",
        )

    assert result == expected
    http.post.assert_called_once()
    call_args = http.post.call_args
    assert call_args[0][0] == f"{BASE_URL}/v1/train"
    body = call_args[1]["json"]
    assert body["platform_job_id"] == "p-1"
    assert body["preset_id"] == "resnet50"
    assert body["dataset_id"] == "ds-1"
    assert body["model_id"] == ""
    assert body["hyperparameters"] == {}


@pytest.mark.asyncio
async def test_submit_train_with_model_and_hparams() -> None:
    expected = {"job_id": "gpu-3", "status": "accepted", "position": 0}
    http = _mock_http(_response(202, expected))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        result = await client.submit_train(
            platform_job_id="p-2",
            preset_id="preset-a",
            dataset_id="ds-2",
            model_id="model-1",
            hyperparameters={"lr": 0.001},
            artifact_prefix="s3://bucket/artifacts",
        )

    assert result == expected
    body = http.post.call_args[1]["json"]
    assert body["model_id"] == "model-1"
    assert body["hyperparameters"] == {"lr": 0.001}
    assert body["artifact_prefix"] == "s3://bucket/artifacts"


@pytest.mark.asyncio
async def test_submit_train_idempotent_resubmit_409() -> None:
    """GPU worker returns 409 for duplicate platform_job_id — client returns body."""
    expected = {"job_id": "gpu-existing", "status": "already_submitted", "detail": "..."}
    http = _mock_http(_response(409, expected))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        result = await client.submit_train(
            platform_job_id="p-dup",
            preset_id="preset-a",
            dataset_id="ds-3",
        )

    assert result == expected
    assert isinstance(result.get("job_id"), str) and result["job_id"]


@pytest.mark.asyncio
async def test_submit_train_409_already_submitted_without_job_id_raises() -> None:
    """409 with ``status == "already_submitted"`` but missing job_id is NOT idempotent success.

    The client must require a non-empty ``job_id`` alongside ``status`` for the
    duplicate/idempotent path.  Malformed or incomplete idempotency responses
    must raise GpuWorkerClientError.
    """
    malformed = {"status": "already_submitted", "detail": "incomplete"}
    http = _mock_http(_response(409, malformed))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(GpuWorkerClientError, match="missing valid job_id"):
            await client.submit_train(
                platform_job_id="p-dup",
                preset_id="preset-a",
                dataset_id="ds-1",
            )


@pytest.mark.asyncio
async def test_submit_train_concurrent_conflict_409_raises() -> None:
    """GPU worker returns 409 for different-job concurrent conflict — client raises error.

    The concurrent-conflict shape lacks ``status`` and ``job_id`` fields;
    it only has ``{"detail": "A training job is already running..."}``.
    The client must NOT treat this as idempotent success.
    """
    conflict = {"detail": "A training job is already running. Only one training job may be active at a time."}
    http = _mock_http(_response(409, conflict))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(GpuWorkerClientError, match="rejected training job"):
            await client.submit_train(
                platform_job_id="p-new",
                preset_id="preset-a",
                dataset_id="ds-1",
            )


@pytest.mark.asyncio
async def test_submit_train_409_with_unparseable_body_raises() -> None:
    r = _response(409, text="raw error")
    r.json = MagicMock(side_effect=ValueError("not json"))  # simulate parse failure
    http = _mock_http(r)

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(GpuWorkerClientError, match="rejected training job"):
            await client.submit_train(
                platform_job_id="p-1",
                preset_id="preset-a",
                dataset_id="ds-1",
            )


# ── get_train_status ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_train_status_success() -> None:
    expected = {
        "job_id": "gpu-1",
        "platform_job_id": "p-1",
        "status": "running",
        "progress": 0.5,
        "metrics": {},
        "error": None,
        "created_at": "2024-01-01T00:00:00Z",
        "started_at": "2024-01-01T00:00:10Z",
        "updated_at": "2024-01-01T00:01:00Z",
    }
    http = _mock_http(_response(200, expected))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        result = await client.get_train_status("gpu-1")

    assert result == expected
    http.get.assert_called_once_with(f"{BASE_URL}/v1/train/gpu-1", params=None)


@pytest.mark.asyncio
async def test_get_train_status_not_found() -> None:
    http = _mock_http(_response(404, {"detail": "not found"}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(GpuWorkerClientError, match="not found"):
            await client.get_train_status("nonexistent")


# ── cancel_train ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_train_success() -> None:
    expected = {"job_id": "gpu-1", "status": "cancelled"}
    http = _mock_http(_response(200, expected))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        result = await client.cancel_train("gpu-1")

    assert result == expected
    http.post.assert_called_once_with(
        f"{BASE_URL}/v1/train/gpu-1/cancel", json=None, params=None
    )


@pytest.mark.asyncio
async def test_cancel_train_not_found() -> None:
    http = _mock_http(_response(404, {"detail": "not found"}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(GpuWorkerClientError, match="not found"):
            await client.cancel_train("nonexistent")


@pytest.mark.asyncio
async def test_cancel_train_terminal_state_409() -> None:
    http = _mock_http(_response(409, {"detail": "terminal state"}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(GpuWorkerClientError, match="terminal state"):
            await client.cancel_train("done-job")


# ── get_train_logs ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_train_logs_success() -> None:
    expected = {
        "job_id": "gpu-1",
        "logs": [
            {"timestamp": "2024-01-01T00:00:00Z", "level": "INFO", "message": "start"},
        ],
    }
    http = _mock_http(_response(200, expected))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        result = await client.get_train_logs("gpu-1", tail=50)

    assert result == expected
    http.get.assert_called_once_with(
        f"{BASE_URL}/v1/train/gpu-1/logs", params={"tail": 50}
    )


@pytest.mark.asyncio
async def test_get_train_logs_default_tail() -> None:
    http = _mock_http(_response(200, {"job_id": "gpu-1", "logs": []}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        await client.get_train_logs("gpu-1")

    http.get.assert_called_once_with(
        f"{BASE_URL}/v1/train/gpu-1/logs", params={"tail": 100}
    )


@pytest.mark.asyncio
async def test_get_train_logs_not_found() -> None:
    http = _mock_http(_response(404, {"detail": "not found"}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(GpuWorkerClientError, match="not found"):
            await client.get_train_logs("nonexistent")


# ── predict_batch (compatibility) ────────────────────────────────────


@pytest.mark.asyncio
async def test_predict_batch_payload_matches_inference_worker() -> None:
    expected_predictions = [
        {"sample_id": "s1", "label": "cat", "confidence": 0.9, "scores": {"cat": 0.9}},
    ]
    http = _mock_http(_response(200, {"predictions": expected_predictions}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        result = await client.predict_batch(
            model_id="m1",
            model_uri="s3://model.pt",
            model_format="pytorch",
            model_metadata={"key": "val"},
            model_bytes=b"fake-model",
            target="classification",
            label_space=["cat", "dog"],
            samples=[
                {
                    "sample_id": "s1",
                    "image_bytes": b"\x89PNG",
                    "metadata": {},
                    "image_uris": [],
                    "question": "",
                    "text": None,
                }
            ],
        )

    assert result == expected_predictions
    body = http.post.call_args[1]["json"]
    assert body["target"] == "classification"
    assert body["label_space"] == ["cat", "dog"]
    assert body["model"]["id"] == "m1"
    assert body["model"]["uri"] == "s3://model.pt"
    assert len(body["samples"]) == 1


@pytest.mark.asyncio
async def test_predict_batch_rejects_invalid_payload() -> None:
    http = _mock_http(_response(200, {"predictions": "not-a-list"}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(ValueError, match="invalid predictions"):
            await client.predict_batch(
                model_id="m1",
                model_uri="s3://m.pt",
                model_format=None,
                model_metadata={},
                model_bytes=b"x",
                target="cls",
                label_space=["a"],
                samples=[],
            )


@pytest.mark.asyncio
async def test_predict_batch_http_error_surfaces_as_client_error() -> None:
    """Predict HTTP errors (e.g. 500) surface as GpuWorkerClientError, not raw httpx."""
    http = _mock_http(_response(500, {"detail": "internal error"}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(GpuWorkerClientError, match="HTTP 500"):
            await client.predict_batch(
                model_id="m1",
                model_uri="s3://m.pt",
                model_format=None,
                model_metadata={},
                model_bytes=b"x",
                target="cls",
                label_space=["a"],
                samples=[],
            )


# ── embed_batch (compatibility) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_batch_payload_matches_inference_worker() -> None:
    expected_embeddings = [
        {"sample_id": "s1", "embedding": [0.1, 0.2, 0.3]}
    ]
    http = _mock_http(_response(200, {"embeddings": expected_embeddings}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        result = await client.embed_batch(
            model_name="clip-vit",
            samples=[{"sample_id": "s1", "image_bytes": b"\x89PNG"}],
        )

    assert result == expected_embeddings
    body = http.post.call_args[1]["json"]
    assert body["model_name"] == "clip-vit"
    assert len(body["samples"]) == 1


@pytest.mark.asyncio
async def test_embed_batch_rejects_invalid_payload() -> None:
    http = _mock_http(_response(200, {"embeddings": "not-a-list"}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(ValueError, match="invalid embedding"):
            await client.embed_batch(
                model_name="clip",
                samples=[],
            )


@pytest.mark.asyncio
async def test_embed_batch_http_error_surfaces_as_client_error() -> None:
    """Embed HTTP errors (e.g. 500) surface as GpuWorkerClientError, not raw httpx."""
    http = _mock_http(_response(503, {"detail": "service unavailable"}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(GpuWorkerClientError, match="HTTP 503"):
            await client.embed_batch(
                model_name="clip",
                samples=[],
            )


# ── Health ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_body() -> None:
    expected = {"status": "ok", "service": "gpu-worker", "gpu_info": {"available": True}}
    http = _mock_http(_response(200, expected))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        result = await client.health()

    assert result == expected
    http.get.assert_called_once_with(f"{BASE_URL}/health", params=None)


@pytest.mark.asyncio
async def test_health_http_error_surfaces_as_client_error() -> None:
    """Health HTTP errors (e.g. 500) surface as GpuWorkerClientError, not raw httpx."""
    http = _mock_http(_response(502, {"detail": "bad gateway"}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        with pytest.raises(GpuWorkerClientError, match="HTTP 502"):
            await client.health()


# ── Unavailable / retry ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_connect_error_raises_gpu_worker_unavailable() -> None:
    import asyncio as _asyncio

    http = _mock_http()
    http.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    http.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(
            base_url=BASE_URL,
            max_retries=2,
            retry_delay_seconds=0.001,
        )
        with mock.patch.object(_asyncio, "sleep", AsyncMock()) as mock_sleep:
            with pytest.raises(GpuWorkerUnavailableError, match="unreachable"):
                await client.get_train_status("any")

    # Should have tried 3 times (2 retries + 1 initial) and slept twice
    assert http.get.call_count == 3
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_retry_eventually_succeeds() -> None:
    import asyncio as _asyncio

    connect_err = httpx.ConnectError("refused")
    success = _response(200, {"job_id": "gpu-ok", "status": "completed", "platform_job_id": "p-1", "progress": 1.0, "metrics": {}, "error": None, "created_at": None, "started_at": None, "updated_at": None})
    # Fail twice, succeed on third
    http = _mock_http()
    http.get = AsyncMock(side_effect=[connect_err, connect_err, success])

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(
            base_url=BASE_URL,
            max_retries=3,
            retry_delay_seconds=0.001,
        )
        with mock.patch.object(_asyncio, "sleep", AsyncMock()):
            result = await client.get_train_status("gpu-ok")

    assert result["job_id"] == "gpu-ok"
    assert result["status"] == "completed"
    assert http.get.call_count == 3


@pytest.mark.asyncio
async def test_http_errors_are_not_retried() -> None:
    """HTTP-level errors (e.g., 404) should raise immediately without retries."""
    import asyncio as _asyncio

    http = _mock_http(_response(404, {"detail": "not found"}))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(
            base_url=BASE_URL,
            max_retries=5,
            retry_delay_seconds=0.001,
        )
        with mock.patch.object(_asyncio, "sleep", AsyncMock()):
            with pytest.raises(GpuWorkerClientError, match="not found"):
                await client.get_train_status("nope")

    # Only one attempt — no retry on HTTP errors
    assert http.get.call_count == 1


@pytest.mark.asyncio
async def test_timeout_raises_gpu_worker_unavailable() -> None:
    import asyncio as _asyncio

    http = _mock_http()
    http.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(
            base_url=BASE_URL,
            max_retries=1,
            retry_delay_seconds=0.001,
        )
        with mock.patch.object(_asyncio, "sleep", AsyncMock()):
            with pytest.raises(GpuWorkerUnavailableError, match="unreachable"):
                await client.get_train_status("any")


# ── Container wiring ─────────────────────────────────────────────────


@pytest.mark.no_gpu_worker_override
def test_gpu_worker_in_container() -> None:
    """Verify the GpuWorkerClient is wired in the container and reachable.

    Opts out of the ``_mock_gpu_worker`` autouse fixture so the real
    provider is resolved (not the MagicMock mock).
    """
    from app.main import container

    client = container.gpu_worker()
    assert isinstance(client, GpuWorkerClient)


def test_gpu_worker_container_uses_resolved_url() -> None:
    """Container gpu_worker provider uses _resolve_gpu_worker_url."""
    from app.main import container
    from app.core.config import _resolve_gpu_worker_url

    cfg = container.config()
    resolved = _resolve_gpu_worker_url(cfg)
    # In test profile, gpu_worker.base_url is absent and inference.base_url
    # is also absent from test.yaml, so resolved should be "".
    assert isinstance(resolved, str)
