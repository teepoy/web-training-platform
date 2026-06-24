from __future__ import annotations

import json

import httpx
import pytest

from app.shared.infrastructure.prefect.client import PrefectClient


@pytest.mark.asyncio
async def test_filter_flow_runs_does_not_send_queue_or_deployment_filters() -> None:
    requests: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=[])

    client = PrefectClient("http://prefect.example/api")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="http://prefect.example/api",
        transport=httpx.MockTransport(handler),
    )

    try:
        await client.filter_flow_runs(
            work_pool_name="default-cpu",
            work_queue_name="queue-that-prefect-misfilters",
            deployment_id="deployment-that-prefect-misfilters",
            state_types=["PENDING", "SCHEDULED"],
            limit=200,
        )
    finally:
        await client.close()

    assert requests == [
        {
            "flow_runs": {"state": {"type": {"any_": ["PENDING", "SCHEDULED"]}}},
            "limit": 200,
            "sort": "EXPECTED_START_TIME_DESC",
            "work_pools": {"name": {"any_": ["default-cpu"]}},
        }
    ]
