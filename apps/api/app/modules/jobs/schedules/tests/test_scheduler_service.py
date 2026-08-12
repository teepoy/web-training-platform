from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.modules.jobs.schedules.app.services.scheduler import SchedulerService
from app.modules.jobs.schedules.domain.repository import ScheduleRepository
from app.shared.db.models.schedules import ScheduleORM
from app.shared.domain.protocols import PrefectClient


def _prefect() -> SimpleNamespace:
    return SimpleNamespace(
        resolve_existing_flow_id=AsyncMock(return_value="flow-1"),
        create_deployment=AsyncMock(return_value={"id": "deployment-1"}),
        update_deployment=AsyncMock(),
        delete_deployment=AsyncMock(),
        create_flow_run_from_deployment=AsyncMock(),
        count_flow_runs_for_deployments=AsyncMock(return_value=0),
        filter_flow_runs_for_deployments=AsyncMock(return_value=[]),
        get_flow_run=AsyncMock(),
        get_flow_run_logs=AsyncMock(return_value=[]),
    )


def _repository() -> SimpleNamespace:
    repository = SimpleNamespace(
        create_schedule=AsyncMock(),
        list_schedules=AsyncMock(return_value=[]),
        list_schedules_paginated=AsyncMock(return_value=([], 0)),
        get_schedule=AsyncMock(),
        get_schedule_by_prefect_deployment_id=AsyncMock(),
        update_schedule=AsyncMock(),
        delete_schedule=AsyncMock(return_value=True),
    )
    repository.create_schedule.side_effect = lambda row: row
    return repository


def _service(prefect: SimpleNamespace, repository: SimpleNamespace) -> SchedulerService:
    return SchedulerService(
        cast(PrefectClient, prefect),
        cast(ScheduleRepository, repository),
        "https://prefect.example",
    )


def _row(**overrides: object) -> ScheduleORM:
    values: dict[str, object] = {
        "id": "schedule-1",
        "org_id": "org-1",
        "created_by": "user-1",
        "prefect_deployment_id": "deployment-1",
        "name": "Nightly drain",
        "flow_name": "drain-dataset",
        "cron": "0 2 * * *",
        "timezone": "Asia/Shanghai",
        "parameters": {"dataset_id": "dataset-1"},
        "description": "nightly",
        "is_schedule_active": True,
        "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return ScheduleORM(**values)


@pytest.mark.anyio
async def test_create_schedule_uses_approved_executable_deployment() -> None:
    prefect = _prefect()
    repository = _repository()
    service = _service(prefect, repository)

    result = await service.create_schedule(
        org_id="org-1",
        created_by="user-1",
        name="Nightly drain",
        flow_name="drain-dataset",
        cron="0 2 * * *",
        timezone="Asia/Shanghai",
        parameters={"dataset_id": "dataset-1"},
        description="nightly",
    )

    call = prefect.create_deployment.await_args.kwargs
    assert call["flow_id"] == "flow-1"
    assert call["work_pool_name"] == "default-cpu"
    assert call["entrypoint"] == (
        "app.modules.datasets.adapter.flows.drain_dataset:drain_dataset"
    )
    assert call["path"] == ""
    assert call["schedules"] == [
        {
            "schedule": {"cron": "0 2 * * *", "timezone": "Asia/Shanghai"},
            "active": True,
        }
    ]
    assert call["name"].startswith("platform-schedule-")
    assert result["id"] != "deployment-1"
    assert result["prefect_deployment_url"] == (
        "https://prefect.example/deployments/deployment/deployment-1"
    )


@pytest.mark.anyio
async def test_create_schedule_rejects_unregistered_flow() -> None:
    prefect = _prefect()
    repository = _repository()
    service = _service(prefect, repository)

    with pytest.raises(HTTPException) as exc_info:
        await service.create_schedule(
            org_id="org-1",
            created_by="user-1",
            name="arbitrary",
            flow_name="unknown-flow",
            cron="0 2 * * *",
        )

    assert exc_info.value.status_code == 422
    prefect.resolve_existing_flow_id.assert_not_awaited()
    prefect.create_deployment.assert_not_awaited()


@pytest.mark.anyio
async def test_create_schedule_compensates_when_database_write_fails() -> None:
    prefect = _prefect()
    repository = _repository()
    repository.create_schedule.side_effect = RuntimeError("database unavailable")
    service = _service(prefect, repository)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await service.create_schedule(
            org_id="org-1",
            created_by="user-1",
            name="Nightly drain",
            flow_name="drain-dataset",
            cron="0 2 * * *",
        )

    prefect.delete_deployment.assert_awaited_once_with("deployment-1")


@pytest.mark.anyio
async def test_update_keeps_internal_prefect_deployment_name() -> None:
    prefect = _prefect()
    repository = _repository()
    existing = _row()
    repository.get_schedule.return_value = existing

    async def update_schedule(*_args: object, **updates: object) -> ScheduleORM:
        for key, value in updates.items():
            setattr(existing, key, value)
        return existing

    repository.update_schedule.side_effect = update_schedule
    service = _service(prefect, repository)

    result = await service.update_schedule(
        "schedule-1",
        {
            "name": "Renamed",
            "cron": "30 3 * * *",
            "timezone": "UTC",
        },
        "org-1",
    )

    prefect.update_deployment.assert_awaited_once_with(
        "deployment-1",
        {
            "schedules": [
                {
                    "schedule": {"cron": "30 3 * * *", "timezone": "UTC"},
                    "active": True,
                }
            ]
        },
    )
    assert result["name"] == "Renamed"


@pytest.mark.anyio
async def test_delete_is_retryable_when_prefect_deployment_is_already_gone() -> None:
    prefect = _prefect()
    repository = _repository()
    repository.get_schedule.return_value = _row()
    prefect.delete_deployment.side_effect = HTTPException(
        status_code=404,
        detail="deployment not found",
    )
    service = _service(prefect, repository)

    await service.delete_schedule("schedule-1", "org-1")

    repository.delete_schedule.assert_awaited_once_with("schedule-1", "org-1")


@pytest.mark.anyio
async def test_run_logs_require_schedule_ownership() -> None:
    prefect = _prefect()
    repository = _repository()
    prefect.get_flow_run.return_value = {
        "id": "run-1",
        "deployment_id": "deployment-1",
    }
    repository.get_schedule_by_prefect_deployment_id.return_value = None
    service = _service(prefect, repository)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_run_logs("run-1", "other-org")

    assert exc_info.value.status_code == 404
    prefect.get_flow_run_logs.assert_not_awaited()


@pytest.mark.anyio
async def test_run_logs_are_loaded_after_ownership_check() -> None:
    prefect = _prefect()
    repository = _repository()
    prefect.get_flow_run.return_value = {
        "id": "run-1",
        "deployment_id": "deployment-1",
    }
    prefect.get_flow_run_logs.return_value = [{"message": "ok"}]
    repository.get_schedule_by_prefect_deployment_id.return_value = _row()
    service = _service(prefect, repository)

    logs = await service.get_run_logs("run-1", "org-1", limit=25)

    assert logs == [{"message": "ok"}]
    prefect.get_flow_run_logs.assert_awaited_once_with("run-1", limit=25)
