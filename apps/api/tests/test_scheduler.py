"""Unit tests for SchedulerService.

Tests mock out httpx.AsyncClient.request so no real Prefect server is needed.
All async tests use pytest-asyncio (@pytest.mark.asyncio).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.services.scheduler import SchedulerService


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

MOCK_DEPLOYMENT = {
    "id": "dep-uuid-1234",
    "name": "test-schedule",
    "flow_id": "flow-uuid-5678",
    "flow_name": "drain-dataset",
    "schedules": [{"schedule": {"cron": "*/5 * * * *"}, "active": True}],
    "parameters": {},
    "description": "test description",
    "paused": False,
    "created": "2026-04-01T00:00:00Z",
    "updated": "2026-04-01T00:00:00Z",
}

MOCK_RUN = {
    "id": "run-uuid-1234",
    "name": "drain-dataset-run",
    "deployment_id": "dep-uuid-1234",
    "flow_name": "drain-dataset",
    "state_type": "COMPLETED",
    "state_name": "Completed",
    "start_time": "2026-04-01T00:00:00Z",
    "end_time": "2026-04-01T00:00:05Z",
    "total_run_time": 5.0,
    "parameters": {},
}

MOCK_LOG = {
    "id": "log-uuid-1234",
    "flow_run_id": "run-uuid-1234",
    "level": 20,
    "timestamp": "2026-04-01T00:00:01Z",
    "message": "Starting drain-dataset flow",
}


def _make_response(status_code: int, json_body=None, text: str = "") -> MagicMock:
    """Return a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.text = text
    return resp


@pytest.fixture()
def svc() -> SchedulerService:
    return SchedulerService(prefect_api_url="http://prefect-test/api")


# ---------------------------------------------------------------------------
# list_schedules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_schedules_returns_list(svc: SchedulerService) -> None:
    deployments = [MOCK_DEPLOYMENT]
    responses = [
        _make_response(200, deployments),  # POST /deployments/filter
        _make_response(200, MOCK_FLOW),    # GET /flows/{id} for enrichment
    ]
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.side_effect = responses
        result = await svc.list_schedules()

    assert len(result) == 1
    assert result[0]["flow_name"] == "drain-dataset"
    first_call = mock_req.call_args_list[0]
    assert first_call[0][0] == "POST"
    assert "/deployments/filter" in first_call[0][1]


@pytest.mark.asyncio
async def test_list_schedules_returns_empty_on_non_list(svc: SchedulerService) -> None:
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = _make_response(200, {"some": "dict"})
        result = await svc.list_schedules()

    assert result == []


# ---------------------------------------------------------------------------
# get_schedule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_schedule_returns_deployment(svc: SchedulerService) -> None:
    responses = [
        _make_response(200, MOCK_DEPLOYMENT.copy()),  # GET /deployments/{id}
        _make_response(200, MOCK_FLOW),                # GET /flows/{id}
    ]
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.side_effect = responses
        result = await svc.get_schedule("dep-uuid-1234")

    assert result["id"] == "dep-uuid-1234"
    assert result["flow_name"] == "drain-dataset"
    first_call = mock_req.call_args_list[0]
    assert first_call[0][0] == "GET"
    assert "dep-uuid-1234" in first_call[0][1]


@pytest.mark.asyncio
async def test_get_schedule_404_raises_http_exception(svc: SchedulerService) -> None:
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = _make_response(404)
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_schedule("nonexistent-id")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "schedule not found"


# ---------------------------------------------------------------------------
# create_schedule
# ---------------------------------------------------------------------------


MOCK_FLOW = {"id": "flow-uuid-5678", "name": "drain-dataset"}


@pytest.mark.asyncio
async def test_create_schedule_sends_correct_body(svc: SchedulerService) -> None:
    flow_filter_resp = _make_response(200, [MOCK_FLOW])
    deployment_resp = _make_response(200, MOCK_DEPLOYMENT)
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.side_effect = [flow_filter_resp, deployment_resp]
        result = await svc.create_schedule(
            name="test-schedule",
            flow_name="drain-dataset",
            cron="*/5 * * * *",
            parameters={"key": "val"},
            description="test description",
        )

    assert result["flow_name"] == "drain-dataset"
    # First call: resolve flow id
    first_call = mock_req.call_args_list[0]
    assert first_call[0][0] == "POST"
    assert "/flows/filter" in first_call[0][1]
    # Second call: create deployment
    second_call = mock_req.call_args_list[1]
    assert second_call[0][0] == "POST"
    assert "/deployments/" in second_call[0][1]
    body = second_call[1]["json"]
    assert body["name"] == "test-schedule"
    assert body["flow_id"] == "flow-uuid-5678"
    assert body["schedules"][0]["schedule"]["cron"] == "*/5 * * * *"
    assert body["parameters"] == {"key": "val"}
    assert body["description"] == "test description"


@pytest.mark.asyncio
async def test_create_schedule_default_parameters(svc: SchedulerService) -> None:
    """parameters defaults to {} when not provided."""
    flow_filter_resp = _make_response(200, [MOCK_FLOW])
    deployment_resp = _make_response(200, MOCK_DEPLOYMENT)
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.side_effect = [flow_filter_resp, deployment_resp]
        await svc.create_schedule(
            name="s", flow_name="drain-dataset", cron="0 * * * *"
        )

    body = mock_req.call_args_list[1][1]["json"]
    assert body["parameters"] == {}


# ---------------------------------------------------------------------------
# delete_schedule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_schedule_returns_none(svc: SchedulerService) -> None:
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = _make_response(204)
        result = await svc.delete_schedule("dep-uuid-1234")

    assert result is None
    call_args = mock_req.call_args
    assert call_args[0][0] == "DELETE"
    assert "dep-uuid-1234" in call_args[0][1]


# ---------------------------------------------------------------------------
# pause_schedule / resume_schedule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_schedule_sends_paused_true(svc: SchedulerService) -> None:
    paused = {**MOCK_DEPLOYMENT, "paused": True}
    # pause calls update_schedule (PATCH) then get_schedule (GET) then
    # _enrich_deployment (GET /flows/{id}) internally
    responses = [
        _make_response(204),              # PATCH
        _make_response(200, paused),      # GET re-fetch deployment
        _make_response(200, MOCK_FLOW),   # GET flow name
    ]
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.side_effect = responses
        result = await svc.pause_schedule("dep-uuid-1234")

    assert result["paused"] is True
    # First call should be PATCH
    first_call = mock_req.call_args_list[0]
    assert first_call[0][0] == "PATCH"
    assert first_call[1]["json"] == {"paused": True}


@pytest.mark.asyncio
async def test_resume_schedule_sends_paused_false(svc: SchedulerService) -> None:
    resumed = {**MOCK_DEPLOYMENT, "paused": False}
    responses = [
        _make_response(204),               # PATCH
        _make_response(200, resumed),      # GET re-fetch deployment
        _make_response(200, MOCK_FLOW),    # GET flow name
    ]
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.side_effect = responses
        result = await svc.resume_schedule("dep-uuid-1234")

    assert result["paused"] is False
    first_call = mock_req.call_args_list[0]
    assert first_call[0][0] == "PATCH"
    assert first_call[1]["json"] == {"paused": False}


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_503_on_connect_error(svc: SchedulerService) -> None:
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.side_effect = httpx.ConnectError("refused")
        with pytest.raises(HTTPException) as exc_info:
            await svc.list_schedules()

    assert exc_info.value.status_code == 503
    assert "unavailable" in exc_info.value.detail


@pytest.mark.asyncio
async def test_502_on_prefect_server_error(svc: SchedulerService) -> None:
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = _make_response(500)
        with pytest.raises(HTTPException) as exc_info:
            await svc.list_schedules()

    assert exc_info.value.status_code == 502
    assert "Prefect server error" in exc_info.value.detail
    assert "500" in exc_info.value.detail


# ---------------------------------------------------------------------------
# get_run_logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_logs_returns_list(svc: SchedulerService) -> None:
    logs = [MOCK_LOG]
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = _make_response(200, logs)
        result = await svc.get_run_logs("run-uuid-1234")

    assert result == logs
    call_args = mock_req.call_args
    assert call_args[0][0] == "POST"
    assert "/logs/filter" in call_args[0][1]
    body = call_args[1]["json"]
    assert "run-uuid-1234" in body["flow_run_id"]["any_"]


@pytest.mark.asyncio
async def test_get_run_logs_empty_on_non_list(svc: SchedulerService) -> None:
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = _make_response(200, None)
        result = await svc.get_run_logs("run-uuid-1234")

    assert result == []


# ---------------------------------------------------------------------------
# trigger_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_run_posts_to_create_flow_run(svc: SchedulerService) -> None:
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = _make_response(200, MOCK_RUN)
        result = await svc.trigger_run("dep-uuid-1234", parameters={"p": 1})

    assert result == MOCK_RUN
    call_args = mock_req.call_args
    assert call_args[0][0] == "POST"
    assert "dep-uuid-1234/create_flow_run" in call_args[0][1]
    assert call_args[1]["json"]["parameters"] == {"p": 1}


@pytest.mark.asyncio
async def test_trigger_run_defaults_empty_parameters(svc: SchedulerService) -> None:
    with patch.object(
        svc._client, "request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = _make_response(200, MOCK_RUN)
        await svc.trigger_run("dep-uuid-1234")

    body = mock_req.call_args[1]["json"]
    assert body["parameters"] == {}
