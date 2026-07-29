from __future__ import annotations

import asyncio
import json

import httpx

from app.shared.infrastructure.prefect.client import PrefectClient


def test_filter_flow_runs_does_not_send_queue_or_deployment_filters() -> None:
    async def run() -> None:
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

    asyncio.run(run())


def test_ensure_deployment_updates_existing_deployment() -> None:
    async def run() -> None:
        requests: list[tuple[str, str, dict[str, object] | None]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            body = (
                json.loads(request.content.decode("utf-8")) if request.content else None
            )
            requests.append((request.method, request.url.path, body))
            if (
                request.method == "POST"
                and request.url.path == "/api/deployments/filter"
            ):
                return httpx.Response(200, json=[{"id": "deployment-1"}])
            if (
                request.method == "PATCH"
                and request.url.path == "/api/deployments/deployment-1"
            ):
                return httpx.Response(204)
            if (
                request.method == "GET"
                and request.url.path == "/api/deployments/deployment-1"
            ):
                return httpx.Response(200, json={"id": "deployment-1"})
            return httpx.Response(500, json={"unexpected": request.url.path})

        client = PrefectClient("http://prefect.example/api")
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            base_url="http://prefect.example/api",
            transport=httpx.MockTransport(handler),
        )

        try:
            deployment = await client.ensure_deployment(
                deployment_name="train-and-predict-deployment",
                flow_name="training-train-and-predict",
                work_pool_name="default-gpu",
                entrypoint="app.workflows.train_predict:train_and_predict_flow",
                path="",
            )
        finally:
            await client.close()

        assert deployment == {"id": "deployment-1"}
        assert requests == [
            (
                "POST",
                "/api/deployments/filter",
                {
                    "deployments": {"name": {"any_": ["train-and-predict-deployment"]}},
                    "limit": 1,
                },
            ),
            (
                "PATCH",
                "/api/deployments/deployment-1",
                {
                    "work_pool_name": "default-gpu",
                    "entrypoint": "app.workflows.train_predict:train_and_predict_flow",
                    "path": "",
                },
            ),
            ("GET", "/api/deployments/deployment-1", None),
        ]

    asyncio.run(run())
