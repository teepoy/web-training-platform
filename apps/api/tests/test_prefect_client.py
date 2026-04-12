from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.services.prefect_client import PrefectClient


def _response(status_code: int, json_body: object = None, text: str = "") -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_body
    response.text = text
    return response


@pytest.mark.asyncio
async def test_request_returns_parsed_json() -> None:
    client = PrefectClient(prefect_api_url="http://prefect.example/api")

    with patch.object(client._client, "request", new_callable=AsyncMock) as request:
        request.return_value = _response(200, {"ok": True})
        result = await client._request("GET", "/health", resource_label="health")

    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_request_returns_none_when_json_not_expected() -> None:
    client = PrefectClient(prefect_api_url="http://prefect.example/api")

    with patch.object(client._client, "request", new_callable=AsyncMock) as request:
        request.return_value = _response(204)
        result = await client._request("DELETE", "/deployments/dep-1", expect_json=False, resource_label="deployment")

    assert result is None


@pytest.mark.asyncio
async def test_request_maps_not_found_to_http_exception() -> None:
    client = PrefectClient(prefect_api_url="http://prefect.example/api")

    with patch.object(client._client, "request", new_callable=AsyncMock) as request:
        request.return_value = _response(404)
        with pytest.raises(HTTPException) as exc_info:
            await client._request("GET", "/flow_runs/missing", resource_label="flow run")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "flow run not found"


@pytest.mark.asyncio
async def test_request_maps_validation_errors_to_http_exception() -> None:
    client = PrefectClient(prefect_api_url="http://prefect.example/api")

    with patch.object(client._client, "request", new_callable=AsyncMock) as request:
        request.return_value = _response(422, text="bad payload")
        with pytest.raises(HTTPException) as exc_info:
            await client._request("POST", "/flow_runs/", json={"invalid": True}, resource_label="flow run")

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Prefect validation error: bad payload"


@pytest.mark.asyncio
async def test_request_maps_server_errors_to_http_exception() -> None:
    client = PrefectClient(prefect_api_url="http://prefect.example/api")

    with patch.object(client._client, "request", new_callable=AsyncMock) as request:
        request.return_value = _response(503)
        with pytest.raises(HTTPException) as exc_info:
            await client._request("GET", "/flow_runs/run-1", resource_label="flow run")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Prefect server error: 503"


@pytest.mark.asyncio
async def test_request_maps_connect_errors_to_service_unavailable() -> None:
    client = PrefectClient(prefect_api_url="http://prefect.example/api")

    with patch.object(client._client, "request", new_callable=AsyncMock) as request:
        request.side_effect = httpx.ConnectError("connection refused")
        with pytest.raises(HTTPException) as exc_info:
            await client._request("GET", "/flow_runs/run-1", resource_label="flow run")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Prefect server unavailable"


@pytest.mark.asyncio
async def test_create_flow_run_from_deployment_includes_idempotency_key() -> None:
    client = PrefectClient(prefect_api_url="http://prefect.example/api")

    with patch.object(client, "_request", new_callable=AsyncMock) as request:
        request.return_value = {"id": "run-1"}
        result = await client.create_flow_run_from_deployment(
            deployment_id="dep-1",
            parameters={"job_id": "job-1"},
            idempotency_key="job-1",
        )

    assert result == {"id": "run-1"}
    request.assert_awaited_once_with(
        "POST",
        "/deployments/dep-1/create_flow_run",
        json={"parameters": {"job_id": "job-1"}, "idempotency_key": "job-1"},
        resource_label="flow run",
    )


@pytest.mark.asyncio
async def test_create_flow_run_from_deployment_omits_idempotency_key_when_absent() -> None:
    client = PrefectClient(prefect_api_url="http://prefect.example/api")

    with patch.object(client, "_request", new_callable=AsyncMock) as request:
        request.return_value = {"id": "run-1"}
        await client.create_flow_run_from_deployment(
            deployment_id="dep-1",
            parameters={"job_id": "job-1"},
        )

    request.assert_awaited_once_with(
        "POST",
        "/deployments/dep-1/create_flow_run",
        json={"parameters": {"job_id": "job-1"}},
        resource_label="flow run",
    )


@pytest.mark.asyncio
async def test_filter_flow_runs_includes_optional_filters() -> None:
    client = PrefectClient(prefect_api_url="http://prefect.example/api")

    with patch.object(client, "_request", new_callable=AsyncMock) as request:
        request.return_value = [{"id": "run-1"}]
        result = await client.filter_flow_runs(
            work_pool_name="training-pool",
            work_queue_name="train-gpu",
            deployment_id="dep-1",
            state_types=["RUNNING", "FAILED"],
            limit=10,
        )

    assert result == [{"id": "run-1"}]
    request.assert_awaited_once_with(
        "POST",
        "/flow_runs/filter",
        json={
            "flow_runs": {
                "work_queue_name": {"any_": ["train-gpu"]},
                "deployment_id": {"any_": ["dep-1"]},
                "state": {"type": {"any_": ["RUNNING", "FAILED"]}},
            },
            "limit": 10,
            "sort": "EXPECTED_START_TIME_DESC",
            "work_pools": {"name": {"any_": ["training-pool"]}},
        },
        resource_label="flow runs",
    )


@pytest.mark.asyncio
async def test_list_task_runs_filters_by_flow_run() -> None:
    client = PrefectClient(prefect_api_url="http://prefect.example/api")

    with patch.object(client, "_request", new_callable=AsyncMock) as request:
        request.return_value = [{"id": "task-run-1"}]
        result = await client.list_task_runs("flow-run-1", limit=25)

    assert result == [{"id": "task-run-1"}]
    request.assert_awaited_once_with(
        "POST",
        "/task_runs/filter",
        json={
            "task_runs": {"flow_run_id": {"any_": ["flow-run-1"]}},
            "limit": 25,
            "sort": "EXPECTED_START_TIME_ASC",
        },
        resource_label="task runs",
    )
