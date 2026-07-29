from __future__ import annotations
# pyright: reportMissingImports=false

import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
from fastapi import HTTPException
from injector import inject

from app.shared.db.registry import ScheduleORM
from app.shared.domain.protocols import PrefectClient

if TYPE_CHECKING:
    from app.modules.jobs.schedules.domain.repository import ScheduleRepository

logger = logging.getLogger(__name__)


def _orm_to_dict(row: ScheduleORM) -> dict[str, object]:
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
            [
                {
                    "schedule": {"cron": row.cron, "timezone": "UTC"},
                    "active": row.is_schedule_active,
                }
            ]
            if row.cron
            else []
        ),
    }


class SchedulerService:
    @inject
    def __init__(
        self,
        prefect_client: PrefectClient,
        repository: ScheduleRepository,
    ) -> None:
        prefect_api_url: str = getattr(
            prefect_client, "_base", "http://localhost:4200/api"
        )
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
        json: dict[str, object] | None = None,
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
        parameters: dict[str, object] | None = None,
        description: str = "",
    ) -> dict[str, object]:
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
        flow_id = await self._resolve_flow_id(flow_name)
        body: dict[str, object] = {
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
        if not isinstance(prefect_deployment_id, str) or not prefect_deployment_id:
            raise HTTPException(
                status_code=502,
                detail="Prefect deployment creation returned no ID",
            )

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

    async def list_schedules(self, org_id: str) -> list[dict[str, object]]:
        """Return schedules for an organization from the local database.

        Parameters
        ----------
        org_id:
            Organization ID to filter schedules.

        Returns
        -------
        list[dict]
            List of schedule data dicts.
        """
        rows = await self._repo.list_schedules(org_id)
        return [_orm_to_dict(r) for r in rows]

    async def list_schedules_paginated(
        self,
        org_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, object]], int]:
        rows, total = await self._repo.list_schedules_paginated(
            org_id,
            offset=offset,
            limit=limit,
        )
        return [_orm_to_dict(row) for row in rows], total

    async def get_schedule(
        self,
        schedule_id: str,
        org_id: str,
    ) -> dict[str, object]:
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
        row = await self._repo.get_schedule(schedule_id, org_id)
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        return _orm_to_dict(row)

    async def update_schedule(
        self,
        schedule_id: str,
        updates: dict[str, object],
        org_id: str,
    ) -> dict[str, object]:
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
        existing = await self._repo.get_schedule(schedule_id, org_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="schedule not found")

        orm_updates: dict[str, object] = {}
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
                first: object = schedules[0]
                if isinstance(first, dict):
                    sched: object = first.get("schedule", {})
                    if isinstance(sched, dict):
                        cron_raw: object = sched.get("cron")
                        if isinstance(cron_raw, str):
                            orm_updates["cron"] = cron_raw

        if existing.prefect_deployment_id:
            await self._request(
                "PATCH",
                f"/deployments/{existing.prefect_deployment_id}",
                json=updates,
                expect_json=False,
            )

        row = await self._repo.update_schedule(
            schedule_id,
            org_id,
            **orm_updates,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        return _orm_to_dict(row)

    async def delete_schedule(self, schedule_id: str, org_id: str) -> None:
        """Delete a schedule from local DB and from Prefect.

        Parameters
        ----------
        schedule_id:
            Local schedule UUID.
        """
        row = await self._repo.get_schedule(schedule_id, org_id)
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")

        if row.prefect_deployment_id:
            await self._request(
                "DELETE",
                f"/deployments/{row.prefect_deployment_id}",
                expect_json=False,
            )
        deleted = await self._repo.delete_schedule(schedule_id, org_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="schedule not found")

    # ------------------------------------------------------------------
    # Flow-run triggering
    # ------------------------------------------------------------------

    async def trigger_run(
        self,
        schedule_id: str,
        org_id: str,
        parameters: dict[str, object] | None = None,
    ) -> dict[str, object]:
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
        row = await self._repo.get_schedule(schedule_id, org_id)
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        deployment_id = row.prefect_deployment_id
        if not deployment_id:
            raise HTTPException(
                status_code=409,
                detail="schedule has no Prefect deployment",
            )

        body: dict[str, object] = {"parameters": parameters or {}}
        return await self._request(
            "POST",
            f"/deployments/{deployment_id}/create_flow_run",
            json=body,
        )

    # ------------------------------------------------------------------
    # Schedule pause / resume
    # ------------------------------------------------------------------

    async def pause_schedule(
        self,
        schedule_id: str,
        org_id: str,
    ) -> dict[str, object]:
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
        existing = await self._repo.get_schedule(schedule_id, org_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        if existing.prefect_deployment_id:
            await self._request(
                "PATCH",
                f"/deployments/{existing.prefect_deployment_id}",
                json={"paused": True},
                expect_json=False,
            )
        row = await self._repo.update_schedule(
            schedule_id,
            org_id,
            is_schedule_active=False,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        return _orm_to_dict(row)

    async def resume_schedule(
        self,
        schedule_id: str,
        org_id: str,
    ) -> dict[str, object]:
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
        existing = await self._repo.get_schedule(schedule_id, org_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        if existing.prefect_deployment_id:
            await self._request(
                "PATCH",
                f"/deployments/{existing.prefect_deployment_id}",
                json={"paused": False},
                expect_json=False,
            )
        row = await self._repo.update_schedule(
            schedule_id,
            org_id,
            is_schedule_active=True,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        return _orm_to_dict(row)

    # ------------------------------------------------------------------
    # Flow-run queries
    # ------------------------------------------------------------------

    async def list_runs(
        self,
        schedule_id: str,
        org_id: str,
        limit: int = 50,
    ) -> list[dict[str, object]]:
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
        row = await self._repo.get_schedule(schedule_id, org_id)
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        deployment_id = row.prefect_deployment_id
        if not deployment_id:
            raise HTTPException(
                status_code=409,
                detail="schedule has no Prefect deployment",
            )

        body: dict[str, object] = {
            "deployments": {"id": {"any_": [deployment_id]}},
            "limit": limit,
            "sort": "EXPECTED_START_TIME_DESC",
        }
        result = await self._request(
            "POST", "/flow_runs/filter", json=body, resource_label="flow run"
        )
        return result if isinstance(result, list) else []

    async def list_runs_for_schedules_paginated(
        self,
        org_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, object]], int]:
        schedules = await self._repo.list_schedules(org_id)
        schedules_by_deployment = {
            schedule.prefect_deployment_id: schedule
            for schedule in schedules
            if schedule.prefect_deployment_id
        }
        deployment_ids = list(schedules_by_deployment)
        if not deployment_ids:
            return [], 0

        deployment_filter = {"id": {"any_": deployment_ids}}
        total_raw = await self._request(
            "POST",
            "/flow_runs/count",
            json={"deployments": deployment_filter},
            resource_label="flow run count",
        )
        if not isinstance(total_raw, int):
            raise HTTPException(
                status_code=502,
                detail="Prefect flow run count returned an invalid response",
            )
        result = await self._request(
            "POST",
            "/flow_runs/filter",
            json={
                "deployments": deployment_filter,
                "offset": offset,
                "limit": limit,
                "sort": "EXPECTED_START_TIME_DESC",
            },
            resource_label="flow runs",
        )
        if not isinstance(result, list):
            raise HTTPException(
                status_code=502,
                detail="Prefect flow run listing returned an invalid response",
            )

        enriched: list[dict[str, object]] = []
        for run in result:
            if not isinstance(run, dict):
                continue
            deployment_id = run.get("deployment_id")
            if not isinstance(deployment_id, str):
                continue
            schedule = schedules_by_deployment.get(deployment_id)
            if schedule is None:
                continue
            enriched.append(
                {
                    **run,
                    "schedule_id": schedule.id,
                    "schedule_name": schedule.name,
                    "created_by": schedule.created_by,
                    "flow_name": run.get("flow_name") or schedule.flow_name,
                    "schedule_created_at": schedule.created_at,
                }
            )
        return enriched, total_raw

    async def get_run(
        self,
        run_id: str,
        org_id: str,
    ) -> dict[str, object]:
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
        run = await self._request(
            "GET", f"/flow_runs/{run_id}", resource_label="flow run"
        )
        if not isinstance(run, dict):
            raise HTTPException(
                status_code=502,
                detail="Prefect flow run lookup returned an invalid response",
            )
        deployment_id = run.get("deployment_id")
        if not isinstance(deployment_id, str) or not deployment_id:
            raise HTTPException(
                status_code=404,
                detail="flow run is not associated with an organization schedule",
            )
        schedule = await self._repo.get_schedule_by_prefect_deployment_id(
            deployment_id,
            org_id,
        )
        if schedule is None:
            raise HTTPException(status_code=404, detail="flow run not found")
        return {
            **run,
            "schedule_id": schedule.id,
            "schedule_name": schedule.name,
            "created_by": schedule.created_by,
            "flow_name": run.get("flow_name") or schedule.flow_name,
            "schedule_created_at": schedule.created_at,
        }

    async def get_run_logs(
        self,
        run_id: str,
        limit: int = 200,
    ) -> list[dict[str, object]]:
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
        body: dict[str, object] = {
            "flow_run_id": {"any_": [run_id]},
            "limit": limit,
        }
        result = await self._request(
            "POST", "/logs/filter", json=body, resource_label="run logs"
        )
        return result if isinstance(result, list) else []
