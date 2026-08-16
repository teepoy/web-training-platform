from __future__ import annotations

import asyncio
import json

import httpx

from app.shared.infrastructure.prefect.client import PrefectClient


def test_get_flow_run_logs_passes_incremental_offset() -> None:
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
            await client.get_flow_run_logs("run-1", limit=50, offset=150)
        finally:
            await client.close()

        assert requests == [
            {
                "logs": {"flow_run_id": {"any_": ["run-1"]}},
                "limit": 50,
                "offset": 150,
                "sort": "TIMESTAMP_ASC",
            }
        ]

    asyncio.run(run())


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


def test_ensure_work_queue_reconciles_priority() -> None:
    async def run() -> None:
        requests: list[tuple[str, str, dict[str, object] | None]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            body = (
                json.loads(request.content.decode("utf-8")) if request.content else None
            )
            requests.append((request.method, request.url.path, body))
            if request.url.path == "/api/work_queues/filter":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "queue-1",
                            "name": "prediction-manual",
                            "priority": 5,
                        }
                    ],
                )
            if (
                request.method == "PATCH"
                and request.url.path
                == "/api/work_pools/default-gpu/queues/prediction-manual"
            ):
                return httpx.Response(204)
            return httpx.Response(500, json={"unexpected": request.url.path})

        client = PrefectClient("http://prefect.example/api")
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            base_url="http://prefect.example/api",
            transport=httpx.MockTransport(handler),
        )
        try:
            queue = await client.ensure_work_queue(
                "default-gpu",
                "prediction-manual",
                priority=1,
            )
        finally:
            await client.close()

        assert queue["priority"] == 1
        assert requests == [
            (
                "POST",
                "/api/work_queues/filter",
                {
                    "work_queues": {"name": {"any_": ["prediction-manual"]}},
                    "limit": 1,
                    "work_pools": {"name": {"any_": ["default-gpu"]}},
                },
            ),
            (
                "PATCH",
                "/api/work_pools/default-gpu/queues/prediction-manual",
                {"priority": 1},
            ),
        ]

    asyncio.run(run())


def test_schedule_deployment_operations_use_explicit_runtime_fields() -> None:
    async def run() -> None:
        requests: list[tuple[str, str, dict[str, object] | None]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            body = (
                json.loads(request.content.decode("utf-8")) if request.content else None
            )
            requests.append((request.method, request.url.path, body))
            if request.method == "POST" and request.url.path == "/api/deployments/":
                return httpx.Response(201, json={"id": "deployment-1"})
            return httpx.Response(204)

        client = PrefectClient("http://prefect.example/api")
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            base_url="http://prefect.example/api",
            transport=httpx.MockTransport(handler),
        )
        try:
            created = await client.create_deployment(
                name="platform-schedule-schedule-1",
                flow_id="flow-1",
                work_pool_name="default-cpu",
                entrypoint="module:flow",
                path="",
                schedules=[
                    {
                        "schedule": {"cron": "0 2 * * *", "timezone": "UTC"},
                        "active": True,
                    }
                ],
                parameters={"dataset_id": "dataset-1"},
                description="nightly",
                tags=["platform-schedule"],
            )
            await client.update_deployment("deployment-1", {"paused": True})
            await client.delete_deployment("deployment-1")
        finally:
            await client.close()

        assert created == {"id": "deployment-1"}
        assert requests == [
            (
                "POST",
                "/api/deployments/",
                {
                    "name": "platform-schedule-schedule-1",
                    "flow_id": "flow-1",
                    "work_pool_name": "default-cpu",
                    "entrypoint": "module:flow",
                    "path": "",
                    "schedules": [
                        {
                            "schedule": {
                                "cron": "0 2 * * *",
                                "timezone": "UTC",
                            },
                            "active": True,
                        }
                    ],
                    "parameters": {"dataset_id": "dataset-1"},
                    "description": "nightly",
                    "tags": ["platform-schedule"],
                    "enforce_parameter_schema": False,
                },
            ),
            ("PATCH", "/api/deployments/deployment-1", {"paused": True}),
            ("DELETE", "/api/deployments/deployment-1", None),
        ]

    asyncio.run(run())


def test_schedule_flow_run_queries_are_deployment_scoped() -> None:
    async def run() -> None:
        requests: list[tuple[str, dict[str, object]]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            requests.append((request.url.path, body))
            if request.url.path == "/api/flow_runs/count":
                return httpx.Response(200, json=3)
            return httpx.Response(200, json=[{"id": "run-1"}])

        client = PrefectClient("http://prefect.example/api")
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            base_url="http://prefect.example/api",
            transport=httpx.MockTransport(handler),
        )
        try:
            count = await client.count_flow_runs_for_deployments(["deployment-1"])
            runs = await client.filter_flow_runs_for_deployments(
                ["deployment-1"],
                offset=10,
                limit=25,
            )
        finally:
            await client.close()

        assert count == 3
        assert runs == [{"id": "run-1"}]
        assert requests == [
            (
                "/api/flow_runs/count",
                {"deployments": {"id": {"any_": ["deployment-1"]}}},
            ),
            (
                "/api/flow_runs/filter",
                {
                    "deployments": {"id": {"any_": ["deployment-1"]}},
                    "offset": 10,
                    "limit": 25,
                    "sort": "EXPECTED_START_TIME_DESC",
                },
            ),
        ]

    asyncio.run(run())
