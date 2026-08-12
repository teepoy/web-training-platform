from __future__ import annotations

from typing import Protocol


class ScheduleManagementPort(Protocol):
    def list_capabilities(self) -> list[dict[str, str]]: ...

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
    ) -> dict[str, object]: ...

    async def list_schedules(
        self,
        org_id: str,
    ) -> list[dict[str, object]]: ...

    async def list_schedules_paginated(
        self,
        org_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, object]], int]: ...

    async def get_schedule(
        self, schedule_id: str, org_id: str
    ) -> dict[str, object]: ...

    async def update_schedule(
        self,
        schedule_id: str,
        updates: dict[str, object],
        org_id: str,
    ) -> dict[str, object]: ...

    async def delete_schedule(self, schedule_id: str, org_id: str) -> None: ...

    async def trigger_run(
        self,
        schedule_id: str,
        org_id: str,
        parameters: dict[str, object] | None = None,
    ) -> dict[str, object]: ...

    async def pause_schedule(
        self, schedule_id: str, org_id: str
    ) -> dict[str, object]: ...

    async def resume_schedule(
        self, schedule_id: str, org_id: str
    ) -> dict[str, object]: ...

    async def list_runs(
        self,
        schedule_id: str,
        org_id: str,
        limit: int = 50,
    ) -> list[dict[str, object]]: ...

    async def list_runs_for_schedules_paginated(
        self,
        org_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, object]], int]: ...

    async def get_run(
        self,
        run_id: str,
        org_id: str,
    ) -> dict[str, object]: ...

    async def get_run_logs(
        self, run_id: str, org_id: str, limit: int = 200
    ) -> list[dict[str, object]]: ...


__all__ = ["ScheduleManagementPort"]
