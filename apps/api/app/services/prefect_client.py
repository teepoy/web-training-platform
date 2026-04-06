"""Prefect REST API client wrapper for work pool and flow run operations.

This module provides :class:`PrefectClient` — a thin async HTTP client over
the Prefect server REST API (v2/v3 compatible).  It intentionally avoids the
``prefect`` Python SDK so that the API service has no heavyweight runtime
dependency; all communication is done through ``httpx.AsyncClient``.

Responsibilities
----------------
- Ensure work pool existence (create-or-get).
- Resolve flow IDs by name (create on first use).
- Create and manage direct flow runs (bypassing deployments).
- Query flow run state, logs, and filter runs by pool/state.

Error mapping
-------------
- Prefect 404  → ``HTTPException(404, "<resource_label> not found")``
- Prefect 4xx (non-404)  → ``HTTPException(422, "Prefect validation error: <body>")``
- Prefect 5xx  → ``HTTPException(502, "Prefect server error: <status>")``
- Connection / transport error  → ``HTTPException(503, "Prefect server unavailable")``
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException


class PrefectClient:
    """Async client wrapper for the Prefect server REST API.

    Parameters
    ----------
    prefect_api_url:
        Base URL of the Prefect API, e.g. ``http://localhost:4200/api``.
        Trailing slashes are normalised away.
    """

    def __init__(self, prefect_api_url: str) -> None:
        self._base = prefect_api_url.rstrip("/")
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base,
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Context-manager / lifecycle helpers
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> PrefectClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        """Construct a full URL from a relative *path*."""
        return f"{self._base}/{path.lstrip('/')}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        expect_json: bool = True,
        resource_label: str = "resource",
    ) -> Any:
        """Execute an HTTP request and map Prefect errors to HTTPExceptions.

        Parameters
        ----------
        method:
            HTTP verb (``"GET"``, ``"POST"``, ``"PATCH"``, ``"DELETE"``).
        path:
            URL path relative to the Prefect API base URL.
        json:
            Optional request body (will be serialised as JSON).
        expect_json:
            When *True* the response body is returned as parsed JSON.
            When *False* ``None`` is returned (useful for 204 responses).
        resource_label:
            Human-readable label used in 404 error messages, e.g.
            ``"flow run"`` or ``"run logs"``.  Defaults to ``"resource"``.

        Returns
        -------
        dict | list | None
            Parsed JSON response or ``None``.

        Raises
        ------
        HTTPException
            - 404 if Prefect returns 404 (detail: ``"<resource_label> not found"``).
            - 422 if Prefect returns 4xx (non-404) (detail includes response body).
            - 502 if Prefect returns 5xx (detail includes status code).
            - 503 on connection / transport failure.
        """
        url = self._url(path)
        try:
            response = await self._client.request(method, url, json=json)
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail="Prefect server unavailable",
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Prefect server unavailable: {exc}",
            )

        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"{resource_label} not found")
        if 400 <= response.status_code < 500:
            raise HTTPException(
                status_code=422,
                detail=f"Prefect validation error: {response.text or response.status_code}",
            )
        if response.status_code >= 500:
            raise HTTPException(
                status_code=502,
                detail=f"Prefect server error: {response.status_code}",
            )

        if not expect_json:
            return None
        return response.json()

    # ------------------------------------------------------------------
    # Work pool operations
    # ------------------------------------------------------------------

    async def ensure_work_pool(
        self,
        name: str,
        type: str,
        concurrency_limit: int,
    ) -> dict:
        """Create a work pool, or return the existing one on 409 Conflict.

        Parameters
        ----------
        name:
            Work pool name.
        type:
            Work pool type, e.g. ``"process"`` or ``"kubernetes"``.
        concurrency_limit:
            Maximum concurrent flow runs.

        Returns
        -------
        dict
            The work pool object returned by Prefect.
        """
        url = self._url("/work_pools/")
        try:
            resp = await self._client.request(
                "POST",
                url,
                json={"name": name, "type": type, "concurrency_limit": concurrency_limit},
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Prefect server unavailable")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Prefect server unavailable: {exc}")

        if resp.status_code == 409:
            return await self.get_work_pool(name)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="work pool not found")
        if 400 <= resp.status_code < 500:
            raise HTTPException(
                status_code=422,
                detail=f"Prefect validation error: {resp.text or resp.status_code}",
            )
        if resp.status_code >= 500:
            raise HTTPException(
                status_code=502,
                detail=f"Prefect server error: {resp.status_code}",
            )
        return resp.json()

    async def get_work_pool(self, name: str) -> dict:
        """Fetch a single work pool by name.

        Parameters
        ----------
        name:
            Work pool name.

        Returns
        -------
        dict
            The work pool object.
        """
        return await self._request("GET", f"/work_pools/{name}", resource_label="work pool")

    async def list_work_pools(self) -> list[dict]:
        """Return all work pools registered in Prefect.

        Returns
        -------
        list[dict]
            List of work pool objects.
        """
        return await self._request("POST", "/work_pools/filter", json={}, resource_label="work pools")

    # ------------------------------------------------------------------
    # Flow helpers
    # ------------------------------------------------------------------

    async def resolve_flow_id(self, flow_name: str) -> str:
        """Look up a Prefect flow by name, creating it if it doesn't exist.

        Prefect 3.x requires ``flow_id`` (not ``flow_name``) when creating
        flow runs directly.  This helper resolves the name to an ID,
        auto-registering the flow on the server when necessary.

        Parameters
        ----------
        flow_name:
            Exact name of the Prefect flow (e.g. ``"finetune-training"``).

        Returns
        -------
        str
            UUID of the flow.
        """
        # Search for existing flow by name
        result = await self._request(
            "POST",
            "/flows/filter",
            json={
                "flows": {"name": {"any_": [flow_name]}},
                "limit": 1,
            },
        )
        if result:
            return result[0]["id"]

        # Flow not registered yet — create it
        created = await self._request(
            "POST",
            "/flows/",
            json={"name": flow_name},
        )
        return created["id"]

    async def resolve_deployment_id(self, deployment_name: str) -> str | None:
        """Look up a Prefect deployment by name.

        Parameters
        ----------
        deployment_name:
            Exact name of the deployment (e.g. ``"train-job-deployment"``).

        Returns
        -------
        str | None
            UUID of the deployment, or None if not found.
        """
        result = await self._request(
            "POST",
            "/deployments/filter",
            json={
                "deployments": {"name": {"any_": [deployment_name]}},
                "limit": 1,
            },
        )
        if result:
            return result[0]["id"]
        return None

    async def create_flow_run_from_deployment(
        self,
        deployment_id: str,
        parameters: dict,
        idempotency_key: str | None = None,
    ) -> dict:
        """Create a flow run from a deployment.

        Parameters
        ----------
        deployment_id:
            UUID of the Prefect deployment.
        parameters:
            Parameter values for the flow run.
        idempotency_key:
            Optional key to prevent duplicate submissions.

        Returns
        -------
        dict
            The created flow-run object returned by Prefect.
        """
        body: dict[str, Any] = {
            "parameters": parameters,
        }
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        return await self._request(
            "POST",
            f"/deployments/{deployment_id}/create_flow_run",
            json=body,
            resource_label="flow run",
        )

    # ------------------------------------------------------------------
    # Flow run operations
    # ------------------------------------------------------------------

    async def create_flow_run(
        self,
        flow_id: str,
        work_pool_name: str,
        parameters: dict,
        idempotency_key: str | None = None,
    ) -> dict:
        """Create a direct flow run on a work pool (no deployment needed).

        Parameters
        ----------
        flow_id:
            UUID of the registered Prefect flow.
        work_pool_name:
            Name of the work pool to execute on.
        parameters:
            Parameter values for the flow run.
        idempotency_key:
            Optional key to prevent duplicate submissions.

        Returns
        -------
        dict
            The created flow-run object returned by Prefect.
        """
        body: dict[str, Any] = {
            "flow_id": flow_id,
            "work_pool_name": work_pool_name,
            "parameters": parameters,
            "state": {"type": "SCHEDULED"},
        }
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        return await self._request("POST", "/flow_runs/", json=body, resource_label="flow run")

    async def get_flow_run(self, flow_run_id: str) -> dict:
        """Fetch a single flow run by ID.

        Parameters
        ----------
        flow_run_id:
            Prefect flow-run UUID.

        Returns
        -------
        dict
            The flow-run object.
        """
        return await self._request(
            "GET", f"/flow_runs/{flow_run_id}", resource_label="flow run"
        )

    async def get_flow_run_logs(
        self,
        flow_run_id: str,
        limit: int = 200,
    ) -> list[dict]:
        """Retrieve log entries for a flow run.

        Parameters
        ----------
        flow_run_id:
            Prefect flow-run UUID.
        limit:
            Maximum number of log lines to return (default 200).

        Returns
        -------
        list[dict]
            Log entry objects ordered by timestamp ascending.
        """
        body: dict[str, Any] = {
            "logs": {"flow_run_id": {"any_": [flow_run_id]}},
            "limit": limit,
            "sort": "TIMESTAMP_ASC",
        }
        result = await self._request(
            "POST", "/logs/filter", json=body, resource_label="run logs"
        )
        return result if isinstance(result, list) else []

    async def set_flow_run_state(
        self,
        flow_run_id: str,
        state_type: str,
    ) -> dict:
        """Transition a flow run to a new state.

        Parameters
        ----------
        flow_run_id:
            Prefect flow-run UUID.
        state_type:
            Target state type, e.g. ``"CANCELLING"`` or ``"CANCELLED"``.

        Returns
        -------
        dict
            The state transition result returned by Prefect.
        """
        return await self._request(
            "POST",
            f"/flow_runs/{flow_run_id}/set_state",
            json={"state": {"type": state_type}},
            resource_label="flow run state",
        )

    async def filter_flow_runs(
        self,
        work_pool_name: str | None = None,
        state_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Filter flow runs by work pool and/or state.

        Parameters
        ----------
        work_pool_name:
            Optional work pool name to restrict results to.
        state_types:
            Optional list of Prefect state type strings, e.g.
            ``["RUNNING", "SCHEDULED"]``.
        limit:
            Maximum number of results to return (default 50).

        Returns
        -------
        list[dict]
            Flow-run objects ordered by expected start time descending.
        """
        flow_runs_filter: dict[str, Any] = {}
        if work_pool_name is not None:
            flow_runs_filter["work_pool_name"] = {"any_": [work_pool_name]}
        if state_types is not None:
            flow_runs_filter["state"] = {"type": {"any_": state_types}}

        body: dict[str, Any] = {
            "flow_runs": flow_runs_filter,
            "limit": limit,
            "sort": "EXPECTED_START_TIME_DESC",
        }
        result = await self._request(
            "POST", "/flow_runs/filter", json=body, resource_label="flow runs"
        )
        return result if isinstance(result, list) else []
