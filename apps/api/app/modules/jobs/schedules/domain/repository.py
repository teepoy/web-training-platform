from __future__ import annotations

from typing import Protocol

from app.shared.db.models.schedules import ScheduleORM


class ScheduleRepository(Protocol):
    async def create_schedule(self, schedule: ScheduleORM) -> ScheduleORM: ...

    async def list_schedules(self, org_id: str) -> list[ScheduleORM]: ...

    async def list_schedules_paginated(
        self,
        org_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ScheduleORM], int]: ...

    async def get_schedule(
        self,
        schedule_id: str,
        org_id: str | None = None,
    ) -> ScheduleORM | None: ...

    async def get_schedule_by_prefect_deployment_id(
        self,
        prefect_deployment_id: str,
        org_id: str,
    ) -> ScheduleORM | None: ...

    async def update_schedule(
        self,
        schedule_id: str,
        org_id: str,
        **kwargs: object,
    ) -> ScheduleORM | None: ...

    async def delete_schedule(self, schedule_id: str, org_id: str) -> bool: ...
