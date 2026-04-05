"""Prefect REST API client wrapper for cron-based schedule management.

This module provides :class:`SchedulerService` — a thin async HTTP client
over the Prefect server REST API (v2/v3 compatible).  It intentionally avoids
the ``prefect`` Python SDK so that the API service has no heavyweight runtime
dependency; all communication is done through ``httpx.AsyncClient``.

Responsibilities
----------------
- CRUD for Prefect *deployments* (which carry cron schedules).
- Trigger ad-hoc flow runs from a deployment.
- Pause / resume a deployment's schedule.
- Query flow-run state and server-side logs.

Error mapping
-------------
- Prefect 404  → ``HTTPException(404, "<resource_label> not found")``
- Prefect 4xx (non-404)  → ``HTTPException(422, "Prefect validation error: <body>")``
- Prefect 5xx  → ``HTTPException(502, "Prefect server error: <status>")``
- Connection / transport error  → ``HTTPException(503, "Prefect server unavailable")``

Factory
-------
:func:`get_scheduler_service` is a FastAPI-compatible async generator dependency
that reads ``PREFECT_API_URL`` from the environment (default:
``http://localhost:4200/api``) and closes the underlying HTTP client after the
request completes.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import HTTPException


class SchedulerService:
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

    async def __aenter__(self) -> SchedulerService:
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
        resource_label: str = "schedule",
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
            ``"flow run"`` or ``"run logs"``.  Defaults to ``"schedule"``.

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
    # Flow helpers
    # ------------------------------------------------------------------

    async def _resolve_flow_id(self, flow_name: str) -> str:
        """Look up a Prefect flow by name, creating it if it doesn't exist.

        Prefect 3.x requires ``flow_id`` (not ``flow_name``) when creating
        deployments.  This helper resolves the name to an ID, auto-registering
        the flow on the server when necessary so callers don't need to run
        ``flow.serve()`` first.

        Parameters
        ----------
        flow_name:
            Exact name of the Prefect flow (e.g. ``"drain-dataset"``).

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

    async def _resolve_flow_name(self, flow_id: str) -> str:
        """Look up a Prefect flow's name by its UUID.

        Parameters
        ----------
        flow_id:
            UUID of the Prefect flow.

        Returns
        -------
        str
            Name of the flow, or empty string if lookup fails.
        """
        try:
            flow = await self._request("GET", f"/flows/{flow_id}")
            return flow.get("name", "")
        except HTTPException:
            return ""

    async def _enrich_deployment(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Add ``flow_name`` to a Prefect deployment dict.

        Prefect 3.x deployments only carry ``flow_id``.  This helper
        resolves the human-readable name so response mappers can
        include it.
        """
        flow_id = raw.get("flow_id", "")
        if flow_id:
            raw["flow_name"] = await self._resolve_flow_name(flow_id)
        return raw

    # ------------------------------------------------------------------
    # Deployment (schedule) CRUD
    # ------------------------------------------------------------------

    async def create_schedule(
        self,
        name: str,
        flow_name: str,
        cron: str,
        parameters: dict[str, Any] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a Prefect deployment with a cron schedule.

        Parameters
        ----------
        name:
            Deployment name (must be unique per flow).
        flow_name:
            Name of the registered Prefect flow.
        cron:
            Cron expression, e.g. ``"0 * * * *"``.
        parameters:
            Default parameter values for the flow run.
        description:
            Human-readable description stored on the deployment.

        Returns
        -------
        dict
            The created deployment object returned by Prefect.
        """
        flow_id = await self._resolve_flow_id(flow_name)
        body: dict[str, Any] = {
            "name": name,
            "flow_id": flow_id,
            "schedules": [
                {
                    "schedule": {"cron": cron, "timezone": "UTC"},
                    "active": True,
                }
            ],
            "parameters": parameters or {},
            "description": description,
            "enforce_parameter_schema": False,
        }
        raw = await self._request("POST", "/deployments/", json=body)
        raw["flow_name"] = flow_name  # We already know the name
        return raw

    async def list_schedules(self) -> list[dict[str, Any]]:
        """Return all deployments registered in Prefect.

        Returns
        -------
        list[dict]
            List of deployment objects (enriched with ``flow_name``).
        """
        body: dict[str, Any] = {"offset": 0, "limit": 100}
        result = await self._request("POST", "/deployments/filter", json=body)
        if not isinstance(result, list):
            return []
        # Enrich each deployment with flow_name
        return [await self._enrich_deployment(d) for d in result]

    async def get_schedule(self, deployment_id: str) -> dict[str, Any]:
        """Fetch a single deployment by ID.

        Parameters
        ----------
        deployment_id:
            Prefect deployment UUID.

        Returns
        -------
        dict
            The deployment object.
        """
        return await self._enrich_deployment(
            await self._request("GET", f"/deployments/{deployment_id}")
        )

    async def update_schedule(
        self,
        deployment_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Partially update a deployment.

        Parameters
        ----------
        deployment_id:
            Prefect deployment UUID.
        updates:
            Fields to update (merged on top of the existing deployment).

        Returns
        -------
        dict
            The updated deployment object.
        """
        await self._request(
            "PATCH", f"/deployments/{deployment_id}", json=updates, expect_json=False
        )
        # Prefect returns 204 on PATCH; re-fetch the updated object.
        return await self.get_schedule(deployment_id)

    async def delete_schedule(self, deployment_id: str) -> None:
        """Delete a deployment permanently.

        Parameters
        ----------
        deployment_id:
            Prefect deployment UUID.
        """
        await self._request(
            "DELETE", f"/deployments/{deployment_id}", expect_json=False
        )

    # ------------------------------------------------------------------
    # Flow-run triggering
    # ------------------------------------------------------------------

    async def trigger_run(
        self,
        deployment_id: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an ad-hoc flow run from a deployment.

        Parameters
        ----------
        deployment_id:
            Prefect deployment UUID.
        parameters:
            Run-time parameter overrides.

        Returns
        -------
        dict
            The created flow-run object.
        """
        body: dict[str, Any] = {"parameters": parameters or {}}
        return await self._request(
            "POST",
            f"/deployments/{deployment_id}/create_flow_run",
            json=body,
        )

    # ------------------------------------------------------------------
    # Schedule pause / resume
    # ------------------------------------------------------------------

    async def pause_schedule(self, deployment_id: str) -> dict[str, Any]:
        """Disable the cron schedule on a deployment.

        Prefect 3.x uses the ``paused`` boolean field on deployments.

        Parameters
        ----------
        deployment_id:
            Prefect deployment UUID.

        Returns
        -------
        dict
            The updated deployment object.
        """
        return await self.update_schedule(deployment_id, {"paused": True})

    async def resume_schedule(self, deployment_id: str) -> dict[str, Any]:
        """Re-enable the cron schedule on a deployment.

        Prefect 3.x uses the ``paused`` boolean field on deployments.

        Parameters
        ----------
        deployment_id:
            Prefect deployment UUID.

        Returns
        -------
        dict
            The updated deployment object.
        """
        return await self.update_schedule(deployment_id, {"paused": False})

    # ------------------------------------------------------------------
    # Flow-run queries
    # ------------------------------------------------------------------

    async def list_runs(
        self,
        deployment_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List flow runs belonging to a deployment.

        Parameters
        ----------
        deployment_id:
            Prefect deployment UUID.
        limit:
            Maximum number of runs to return (default 50).

        Returns
        -------
        list[dict]
            Flow-run objects ordered by expected start time descending.
        """
        body: dict[str, Any] = {
            "deployments": {"id": {"any_": [deployment_id]}},
            "limit": limit,
            "sort": "EXPECTED_START_TIME_DESC",
        }
        result = await self._request(
            "POST", "/flow_runs/filter", json=body, resource_label="flow run"
        )
        return result if isinstance(result, list) else []

    async def get_run(self, run_id: str) -> dict[str, Any]:
        """Fetch a single flow run by ID.

        Parameters
        ----------
        run_id:
            Prefect flow-run UUID.

        Returns
        -------
        dict
            The flow-run object.
        """
        return await self._request(
            "GET", f"/flow_runs/{run_id}", resource_label="flow run"
        )

    async def get_run_logs(
        self,
        run_id: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Retrieve log entries for a flow run.

        Parameters
        ----------
        run_id:
            Prefect flow-run UUID.
        limit:
            Maximum number of log lines to return (default 200).

        Returns
        -------
        list[dict]
            Log entry objects as returned by Prefect.
        """
        body: dict[str, Any] = {
            "flow_run_id": {"any_": [run_id]},
            "limit": limit,
        }
        result = await self._request(
            "POST", "/logs/filter", json=body, resource_label="run logs"
        )
        return result if isinstance(result, list) else []


# ---------------------------------------------------------------------------
# FastAPI dependency factory
# ---------------------------------------------------------------------------


async def get_scheduler_service() -> AsyncGenerator[SchedulerService, None]:
    """FastAPI async generator dependency for :class:`SchedulerService`.

    Reads ``PREFECT_API_URL`` from the environment.  Falls back to
    ``http://localhost:4200/api`` when the variable is not set.  The
    underlying ``httpx.AsyncClient`` is closed after each request via the
    generator's ``finally`` block.

    Usage
    -----
    .. code-block:: python

        from fastapi import Depends
        from app.services.scheduler import SchedulerService, get_scheduler_service

        @app.get("/schedules")
        async def list_schedules(
            svc: SchedulerService = Depends(get_scheduler_service),
        ) -> list[dict]:
            return await svc.list_schedules()
    """
    prefect_api_url = os.environ.get(
        "PREFECT_API_URL", "http://localhost:4200/api"
    )
    svc = SchedulerService(prefect_api_url=prefect_api_url)
    try:
        yield svc
    finally:
        await svc.close()
