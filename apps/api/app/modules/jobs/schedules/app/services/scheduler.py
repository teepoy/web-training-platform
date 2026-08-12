from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import HTTPException
from injector import inject

from app.modules.jobs.schedules.domain.validation import (
    validate_cron_expression,
    validate_iana_timezone,
)
from app.shared.db.registry import ScheduleORM
from app.shared.domain.protocols import PrefectClient
from app.shared.infrastructure.prefect.deployments import (
    get_schedulable_prefect_deployment,
    schedulable_prefect_deployment_specs,
)

if TYPE_CHECKING:
    from app.modules.jobs.schedules.domain.repository import ScheduleRepository

logger = logging.getLogger(__name__)


def _prefect_schedule(cron: str, timezone: str) -> dict[str, object]:
    return {
        "schedule": {"cron": cron, "timezone": timezone},
        "active": True,
    }


def _validate_cron_timezone(cron: str, timezone: str) -> None:
    try:
        validate_cron_expression(cron)
        validate_iana_timezone(timezone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _prefect_deployment_url(ui_base: str, deployment_id: str | None) -> str | None:
    if not deployment_id:
        return None
    return f"{ui_base.rstrip('/')}/deployments/deployment/{deployment_id}"


def _orm_to_dict(row: ScheduleORM, prefect_ui_url: str) -> dict[str, object]:
    return {
        "id": row.id,
        "name": row.name,
        "flow_name": row.flow_name,
        "cron": row.cron,
        "timezone": row.timezone,
        "parameters": row.parameters or {},
        "description": row.description or "",
        "is_schedule_active": row.is_schedule_active,
        "prefect_deployment_id": row.prefect_deployment_id,
        "prefect_deployment_url": _prefect_deployment_url(
            prefect_ui_url,
            row.prefect_deployment_id,
        ),
        "org_id": row.org_id,
        "created_by": row.created_by,
        "created": row.created_at.isoformat() if row.created_at else None,
        "updated": row.updated_at.isoformat() if row.updated_at else None,
    }


class SchedulerService:
    @inject
    def __init__(
        self,
        prefect_client: PrefectClient,
        repository: ScheduleRepository,
        prefect_ui_url: str,
    ) -> None:
        self._prefect = prefect_client
        self._repo = repository
        self._prefect_ui_url = prefect_ui_url.rstrip("/")

    def list_capabilities(self) -> list[dict[str, str]]:
        return [
            {
                "flow_name": spec.flow_name,
                "deployment_name": spec.deployment_name,
            }
            for spec in schedulable_prefect_deployment_specs()
        ]

    async def create_schedule(
        self,
        org_id: str,
        created_by: str,
        name: str,
        flow_name: str,
        cron: str,
        timezone: str = "UTC",
        parameters: dict[str, object] | None = None,
        description: str = "",
    ) -> dict[str, object]:
        if not name.strip():
            raise HTTPException(
                status_code=422, detail="schedule name must not be empty"
            )
        _validate_cron_timezone(cron, timezone)
        spec = get_schedulable_prefect_deployment(flow_name)
        if spec is None:
            supported = ", ".join(
                candidate.flow_name
                for candidate in schedulable_prefect_deployment_specs()
            )
            raise HTTPException(
                status_code=422,
                detail=(
                    f"flow {flow_name!r} is not schedulable; "
                    f"supported flows: {supported}"
                ),
            )

        flow_id = await self._prefect.resolve_existing_flow_id(spec.flow_name)
        if flow_id is None:
            raise HTTPException(
                status_code=503,
                detail=f"schedulable Prefect flow {spec.flow_name!r} is unavailable",
            )

        schedule_id = str(uuid4())
        raw = await self._prefect.create_deployment(
            name=f"platform-schedule-{schedule_id}",
            flow_id=flow_id,
            work_pool_name=spec.work_pool_name,
            entrypoint=spec.entrypoint,
            path=spec.path,
            schedules=[_prefect_schedule(cron, timezone)],
            parameters=parameters or {},
            description=description,
            tags=[
                "platform-schedule",
                f"platform-org:{org_id}",
                f"platform-schedule-id:{schedule_id}",
            ],
        )
        prefect_deployment_id = raw.get("id")
        if not isinstance(prefect_deployment_id, str) or not prefect_deployment_id:
            raise HTTPException(
                status_code=502,
                detail="Prefect deployment creation returned no ID",
            )

        orm = ScheduleORM(
            id=schedule_id,
            org_id=org_id,
            created_by=created_by,
            prefect_deployment_id=prefect_deployment_id,
            name=name,
            flow_name=flow_name,
            cron=cron,
            timezone=timezone,
            parameters=parameters or {},
            description=description,
            is_schedule_active=True,
        )
        try:
            orm = await self._repo.create_schedule(orm)
        except Exception:
            try:
                await self._prefect.delete_deployment(prefect_deployment_id)
            except Exception:
                logger.exception(
                    "Failed to compensate Prefect deployment %s after schedule "
                    "persistence failure",
                    prefect_deployment_id,
                )
            raise
        return _orm_to_dict(orm, self._prefect_ui_url)

    async def list_schedules(self, org_id: str) -> list[dict[str, object]]:
        rows = await self._repo.list_schedules(org_id)
        return [_orm_to_dict(row, self._prefect_ui_url) for row in rows]

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
        return (
            [_orm_to_dict(row, self._prefect_ui_url) for row in rows],
            total,
        )

    async def get_schedule(
        self,
        schedule_id: str,
        org_id: str,
    ) -> dict[str, object]:
        row = await self._repo.get_schedule(schedule_id, org_id)
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        return _orm_to_dict(row, self._prefect_ui_url)

    async def update_schedule(
        self,
        schedule_id: str,
        updates: dict[str, object],
        org_id: str,
    ) -> dict[str, object]:
        existing = await self._repo.get_schedule(schedule_id, org_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="schedule not found")

        if "name" in updates and not str(updates["name"]).strip():
            raise HTTPException(
                status_code=422, detail="schedule name must not be empty"
            )
        if "cron" in updates or "timezone" in updates:
            _validate_cron_timezone(
                str(updates.get("cron", existing.cron or "")),
                str(updates.get("timezone", existing.timezone)),
            )

        orm_updates = self._orm_updates(updates)
        prefect_updates = self._prefect_updates(existing, updates)
        deployment_id = existing.prefect_deployment_id
        prefect_updated = False
        if deployment_id and prefect_updates:
            await self._prefect.update_deployment(deployment_id, prefect_updates)
            prefect_updated = True

        try:
            row = await self._repo.update_schedule(
                schedule_id,
                org_id,
                **orm_updates,
            )
        except Exception:
            if deployment_id and prefect_updated:
                await self._rollback_prefect_update(existing)
            raise
        if row is None:
            if deployment_id and prefect_updated:
                await self._rollback_prefect_update(existing)
            raise HTTPException(status_code=404, detail="schedule not found")
        return _orm_to_dict(row, self._prefect_ui_url)

    def _orm_updates(self, updates: dict[str, object]) -> dict[str, object]:
        allowed = {
            "name",
            "description",
            "parameters",
            "cron",
            "timezone",
            "is_schedule_active",
        }
        return {key: value for key, value in updates.items() if key in allowed}

    def _prefect_updates(
        self,
        existing: ScheduleORM,
        updates: dict[str, object],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key in ("description", "parameters"):
            if key in updates:
                result[key] = updates[key]
        if "is_schedule_active" in updates:
            result["paused"] = not bool(updates["is_schedule_active"])
        if "cron" in updates or "timezone" in updates:
            cron = str(updates.get("cron", existing.cron or ""))
            timezone = str(updates.get("timezone", existing.timezone))
            result["schedules"] = [_prefect_schedule(cron, timezone)]
        return result

    async def _rollback_prefect_update(self, existing: ScheduleORM) -> None:
        deployment_id = existing.prefect_deployment_id
        if not deployment_id:
            return
        try:
            await self._prefect.update_deployment(
                deployment_id,
                {
                    "description": existing.description,
                    "parameters": existing.parameters or {},
                    "paused": not existing.is_schedule_active,
                    "schedules": [
                        _prefect_schedule(existing.cron or "", existing.timezone)
                    ],
                },
            )
        except Exception:
            logger.exception(
                "Failed to roll back Prefect deployment %s after schedule "
                "persistence failure",
                deployment_id,
            )

    async def delete_schedule(self, schedule_id: str, org_id: str) -> None:
        row = await self._repo.get_schedule(schedule_id, org_id)
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        if row.prefect_deployment_id:
            try:
                await self._prefect.delete_deployment(row.prefect_deployment_id)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
        deleted = await self._repo.delete_schedule(schedule_id, org_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="schedule not found")

    async def trigger_run(
        self,
        schedule_id: str,
        org_id: str,
        parameters: dict[str, object] | None = None,
    ) -> dict[str, object]:
        row = await self._repo.get_schedule(schedule_id, org_id)
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        deployment_id = row.prefect_deployment_id
        if not deployment_id:
            raise HTTPException(
                status_code=409,
                detail="schedule has no Prefect deployment",
            )
        return await self._prefect.create_flow_run_from_deployment(
            deployment_id,
            parameters or {},
        )

    async def pause_schedule(
        self,
        schedule_id: str,
        org_id: str,
    ) -> dict[str, object]:
        return await self.update_schedule(
            schedule_id,
            {"is_schedule_active": False},
            org_id,
        )

    async def resume_schedule(
        self,
        schedule_id: str,
        org_id: str,
    ) -> dict[str, object]:
        return await self.update_schedule(
            schedule_id,
            {"is_schedule_active": True},
            org_id,
        )

    async def list_runs(
        self,
        schedule_id: str,
        org_id: str,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        row = await self._repo.get_schedule(schedule_id, org_id)
        if row is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        deployment_id = row.prefect_deployment_id
        if not deployment_id:
            raise HTTPException(
                status_code=409,
                detail="schedule has no Prefect deployment",
            )
        return await self._prefect.filter_flow_runs_for_deployments(
            [deployment_id],
            limit=limit,
        )

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

        total = await self._prefect.count_flow_runs_for_deployments(deployment_ids)
        result = await self._prefect.filter_flow_runs_for_deployments(
            deployment_ids,
            offset=offset,
            limit=limit,
        )
        enriched: list[dict[str, object]] = []
        for run in result:
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
        return enriched, total

    async def get_run(
        self,
        run_id: str,
        org_id: str,
    ) -> dict[str, object]:
        run = await self._prefect.get_flow_run(run_id)
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
        org_id: str,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        await self.get_run(run_id, org_id)
        return await self._prefect.get_flow_run_logs(run_id, limit=limit)
