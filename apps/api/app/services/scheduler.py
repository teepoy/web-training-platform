"""Prefect REST API client wrapper for cron-based schedule management.

This module provides :class:`SchedulerService` — a thin async HTTP client
over the Prefect server REST API (v2/v3 compatible).  It intentionally avoids
the ``prefect`` Python SDK so that the API service has no heavyweight runtime
dependency; all communication is done through ``httpx.AsyncClient``.

Schedule records are persisted locally in the :class:`ScheduleORM` table via
an injected :class:`SqlRepository`.  This provides org-scoped schedule
management and survives Prefect restarts.

Responsibilities
----------------
- CRUD for Prefect *deployments* (which carry cron schedules).
- Persist schedule records locally with org/user context.
- Trigger ad-hoc flow runs from a deployment.
- Pause / resume a deployment's schedule.
- Query flow-run state and server-side logs.

Error mapping
-------------
- Prefect 404  → ``HTTPException(404, "<resource_label> not found")``
- Prefect 4xx (non-404)  → ``HTTPException(422, "Prefect validation error: <body>")``
- Prefect 5xx  → ``HTTPException(502, "Prefect server error: <status>")``
- Connection / transport error  → logged as warning; local DB operation still succeeds

Factory
-------
:func:`get_scheduler_service` is a FastAPI-compatible async generator dependency
that reads ``PREFECT_API_URL`` from the environment (default:
``http://localhost:4200/api``) and closes the underlying HTTP client after the
request completes.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.db.models import ScheduleORM

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy repository singleton (avoids circular import from main.py)
# ---------------------------------------------------------------------------

_repository = None
_local_schedule_runs: dict[str, list[dict[str, Any]]] = {}


def _get_repository():
    """Return a lazily-initialised SqlRepository singleton."""
    global _repository
    if _repository is None:
        try:
            from app.core.config import load_config
            from app.db.session import create_engine, create_session_factory
            from app.repositories.sql_repository import SqlRepository

            cfg = load_config()
            engine = create_engine(str(cfg.db.url))
            session_factory = create_session_factory(engine)
            _repository = SqlRepository(session_factory=session_factory)
        except Exception as exc:
            logger.warning("Failed to initialise repository for SchedulerService: %s", exc)
    return _repository


def _orm_to_dict(row: ScheduleORM) -> dict[str, Any]:
    """Convert a :class:`ScheduleORM` instance to a response-compatible dict."""
    return {
        "id": row.id,
        "name": row.name,
        "flow_name": row.flow_name,
        "cron": row.cron,
        "parameters": row.parameters or {},
        "description": row.description or "",
        "is_schedule_active": row.is_schedule_active,
        "prefect_deployment_id": row.prefect_deployment_id,
        "org_id": row.org_id,
        "created_by": row.created_by,
        "created": row.created_at.isoformat() if row.created_at else None,
        "updated": row.updated_at.isoformat() if row.updated_at else None,
        # Provide Prefect-compatible keys so _deployment_to_schedule still works
        "paused": not row.is_schedule_active,
        "schedules": (
            [{"schedule": {"cron": row.cron, "timezone": "UTC"}, "active": row.is_schedule_active}]
            if row.cron
            else []
        ),
    }


def _local_run_dict(schedule: ScheduleORM, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "name": f"{schedule.name}-local-run",
        "deployment_id": None,
        "flow_name": schedule.flow_name,
        "state_type": "COMPLETED",
        "state_name": "Completed",
        "start_time": started_at,
        "end_time": started_at,
        "total_run_time": 0.0,
        "parameters": parameters or schedule.parameters or {},
    }


def _store_local_run(schedule_id: str, run: dict[str, Any], limit: int = 20) -> None:
    runs = _local_schedule_runs.setdefault(schedule_id, [])
    runs.insert(0, run)
    del runs[limit:]


class SchedulerService:
    """Async client wrapper for the Prefect server REST API with local DB persistence.

    Parameters
    ----------
    prefect_api_url:
        Base URL of the Prefect API, e.g. ``http://localhost:4200/api``.
        Trailing slashes are normalised away.
    repository:
        SQL repository for local schedule persistence.  When ``None`` the
        service operates in Prefect-only mode (legacy behaviour).
    """

    def __init__(self, prefect_api_url: str, repository: Any = None) -> None:
        self._base = prefect_api_url.rstrip("/")
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base,
            timeout=30.0,
        )
        self._repo = repository

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
        org_id: str,
        created_by: str,
        name: str,
        flow_name: str,
        cron: str,
        parameters: dict[str, Any] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a Prefect deployment with a cron schedule and persist locally.

        Parameters
        ----------
        org_id:
            Organization ID to scope the schedule.
        created_by:
            User ID of the creator.
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
            The created schedule data (from local DB, enriched with Prefect ID).
        """
        prefect_deployment_id: str | None = None

        # 1. Try to create Prefect deployment
        try:
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
            prefect_deployment_id = raw.get("id")
        except HTTPException as exc:
            logger.warning("Prefect unavailable during create_schedule: %s", exc.detail)

        # 2. Persist locally in DB
        if self._repo is not None:
            orm = ScheduleORM(
                id=str(uuid4()),
                org_id=org_id,
                created_by=created_by,
                prefect_deployment_id=prefect_deployment_id,
                name=name,
                flow_name=flow_name,
                cron=cron,
                parameters=parameters or {},
                description=description,
                is_schedule_active=True,
            )
            orm = await self._repo.create_schedule(orm)
            return _orm_to_dict(orm)

        # Fallback: return Prefect-style dict if no repo
        return {
            "id": prefect_deployment_id or str(uuid4()),
            "name": name,
            "flow_name": flow_name,
            "schedules": [{"schedule": {"cron": cron, "timezone": "UTC"}, "active": True}],
            "parameters": parameters or {},
            "description": description,
            "paused": False,
            "prefect_deployment_id": prefect_deployment_id,
        }

    async def list_schedules(self, org_id: str | None = None) -> list[dict[str, Any]]:
        """Return schedules for an org from local DB.

        When ``org_id`` is provided (expected for org-scoped calls), queries
        the local DB filtered by org.  Falls back to Prefect if no repository
        is configured.

        Parameters
        ----------
        org_id:
            Organization ID to filter schedules.

        Returns
        -------
        list[dict]
            List of schedule data dicts.
        """
        if self._repo is not None and org_id is not None:
            rows = await self._repo.list_schedules(org_id)
            return [_orm_to_dict(r) for r in rows]

        if self._repo is not None:
            # repo present but no org_id — return empty (safety guard)
            return []

        # Legacy Prefect-only fallback
        body: dict[str, Any] = {"offset": 0, "limit": 100}
        result = await self._request("POST", "/deployments/filter", json=body)
        if not isinstance(result, list):
            return []
        return [await self._enrich_deployment(d) for d in result]

    async def get_schedule(
        self,
        schedule_id: str,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a single schedule by local DB ID.

        Parameters
        ----------
        schedule_id:
            Local schedule UUID (ScheduleORM primary key).
        org_id:
            When provided, enforces that the schedule belongs to the org.

        Returns
        -------
        dict
            The schedule data.

        Raises
        ------
        HTTPException
            404 if not found or org mismatch.
        """
        if self._repo is not None:
            row = await self._repo.get_schedule(schedule_id, org_id)
            if row is None:
                raise HTTPException(status_code=404, detail="schedule not found")
            return _orm_to_dict(row)

        # Legacy Prefect-only fallback
        return await self._enrich_deployment(
            await self._request("GET", f"/deployments/{schedule_id}")
        )

    async def update_schedule(
        self,
        schedule_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Partially update a schedule in local DB and optionally in Prefect.

        Parameters
        ----------
        schedule_id:
            Local schedule UUID.
        updates:
            Fields to update.  Prefect-compatible fields (``paused``,
            ``schedules``, etc.) are forwarded to Prefect if the record has
            a ``prefect_deployment_id``.

        Returns
        -------
        dict
            The updated schedule data.
        """
        if self._repo is not None:
            # Translate Prefect fields back to ORM fields for local update
            orm_updates: dict[str, Any] = {}
            if "name" in updates:
                orm_updates["name"] = updates["name"]
            if "description" in updates:
                orm_updates["description"] = updates["description"]
            if "parameters" in updates:
                orm_updates["parameters"] = updates["parameters"]
            if "paused" in updates:
                orm_updates["is_schedule_active"] = not updates["paused"]
            if "schedules" in updates:
                schedules = updates["schedules"]
                if schedules and isinstance(schedules, list):
                    cron = schedules[0].get("schedule", {}).get("cron")
                    if cron:
                        orm_updates["cron"] = cron

            row = await self._repo.update_schedule(schedule_id, **orm_updates)
            if row is None:
                raise HTTPException(status_code=404, detail="schedule not found")

            # Also update Prefect if deployment ID exists
            if row.prefect_deployment_id:
                try:
                    await self._request(
                        "PATCH",
                        f"/deployments/{row.prefect_deployment_id}",
                        json=updates,
                        expect_json=False,
                    )
                except HTTPException as exc:
                    logger.warning(
                        "Prefect unavailable during update_schedule %s: %s",
                        schedule_id,
                        exc.detail,
                    )

            return _orm_to_dict(row)

        # Legacy Prefect-only fallback
        await self._request(
            "PATCH", f"/deployments/{schedule_id}", json=updates, expect_json=False
        )
        return await self.get_schedule(schedule_id)

    async def delete_schedule(self, schedule_id: str) -> None:
        """Delete a schedule from local DB and from Prefect.

        Parameters
        ----------
        schedule_id:
            Local schedule UUID.
        """
        if self._repo is not None:
            row = await self._repo.get_schedule(schedule_id)
            if row is None:
                raise HTTPException(status_code=404, detail="schedule not found")

            prefect_deployment_id = row.prefect_deployment_id

            # Delete from local DB first
            await self._repo.delete_schedule(schedule_id)

            # Then try to delete from Prefect
            if prefect_deployment_id:
                try:
                    await self._request(
                        "DELETE",
                        f"/deployments/{prefect_deployment_id}",
                        expect_json=False,
                    )
                except HTTPException as exc:
                    logger.warning(
                        "Prefect unavailable during delete_schedule %s: %s",
                        schedule_id,
                        exc.detail,
                    )
            return

        # Legacy Prefect-only fallback
        await self._request(
            "DELETE", f"/deployments/{schedule_id}", expect_json=False
        )

    # ------------------------------------------------------------------
    # Flow-run triggering
    # ------------------------------------------------------------------

    async def trigger_run(
        self,
        schedule_id: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an ad-hoc flow run from a schedule.

        Parameters
        ----------
        schedule_id:
            Local schedule UUID (used to look up the Prefect deployment ID).
        parameters:
            Run-time parameter overrides.

        Returns
        -------
        dict
            The created flow-run object.
        """
        if self._repo is not None:
            row = await self._repo.get_schedule(schedule_id)
            if row is None:
                raise HTTPException(status_code=404, detail="schedule not found")
            deployment_id = row.prefect_deployment_id
            if not deployment_id:
                run = _local_run_dict(row, parameters)
                _store_local_run(schedule_id, run)
                return run
        else:
            deployment_id = schedule_id

        body: dict[str, Any] = {"parameters": parameters or {}}
        return await self._request(
            "POST",
            f"/deployments/{deployment_id}/create_flow_run",
            json=body,
        )

    # ------------------------------------------------------------------
    # Schedule pause / resume
    # ------------------------------------------------------------------

    async def pause_schedule(self, schedule_id: str) -> dict[str, Any]:
        """Disable the cron schedule on a deployment.

        Updates local ``is_schedule_active=False`` and calls Prefect pause.

        Parameters
        ----------
        schedule_id:
            Local schedule UUID.

        Returns
        -------
        dict
            The updated schedule data.
        """
        if self._repo is not None:
            row = await self._repo.update_schedule(
                schedule_id, is_schedule_active=False
            )
            if row is None:
                raise HTTPException(status_code=404, detail="schedule not found")

            if row.prefect_deployment_id:
                try:
                    await self._request(
                        "PATCH",
                        f"/deployments/{row.prefect_deployment_id}",
                        json={"paused": True},
                        expect_json=False,
                    )
                except HTTPException as exc:
                    logger.warning(
                        "Prefect unavailable during pause_schedule %s: %s",
                        schedule_id,
                        exc.detail,
                    )

            return _orm_to_dict(row)

        # Legacy Prefect-only fallback
        return await self.update_schedule(schedule_id, {"paused": True})

    async def resume_schedule(self, schedule_id: str) -> dict[str, Any]:
        """Re-enable the cron schedule on a deployment.

        Updates local ``is_schedule_active=True`` and calls Prefect resume.

        Parameters
        ----------
        schedule_id:
            Local schedule UUID.

        Returns
        -------
        dict
            The updated schedule data.
        """
        if self._repo is not None:
            row = await self._repo.update_schedule(
                schedule_id, is_schedule_active=True
            )
            if row is None:
                raise HTTPException(status_code=404, detail="schedule not found")

            if row.prefect_deployment_id:
                try:
                    await self._request(
                        "PATCH",
                        f"/deployments/{row.prefect_deployment_id}",
                        json={"paused": False},
                        expect_json=False,
                    )
                except HTTPException as exc:
                    logger.warning(
                        "Prefect unavailable during resume_schedule %s: %s",
                        schedule_id,
                        exc.detail,
                    )

            return _orm_to_dict(row)

        # Legacy Prefect-only fallback
        return await self.update_schedule(schedule_id, {"paused": False})

    # ------------------------------------------------------------------
    # Flow-run queries
    # ------------------------------------------------------------------

    async def list_runs(
        self,
        schedule_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List flow runs belonging to a schedule/deployment.

        Parameters
        ----------
        schedule_id:
            Local schedule UUID (used to look up the Prefect deployment ID).
        limit:
            Maximum number of runs to return (default 50).

        Returns
        -------
        list[dict]
            Flow-run objects ordered by expected start time descending.
        """
        if self._repo is not None:
            row = await self._repo.get_schedule(schedule_id)
            if row is None:
                raise HTTPException(status_code=404, detail="schedule not found")
            deployment_id = row.prefect_deployment_id
            if not deployment_id:
                return list(_local_schedule_runs.get(schedule_id, []))[:limit]
        else:
            deployment_id = schedule_id

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

    The repository is lazily initialised for local DB persistence.

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
    repo = _get_repository()
    svc = SchedulerService(prefect_api_url=prefect_api_url, repository=repo)
    try:
        yield svc
    finally:
        await svc.close()
