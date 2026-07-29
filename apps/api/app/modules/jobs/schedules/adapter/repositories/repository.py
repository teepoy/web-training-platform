from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.db.models.schedules import ScheduleORM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScheduleSqlRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def create_schedule(self, schedule: ScheduleORM) -> ScheduleORM:
        async with self.session_factory() as session:
            session.add(schedule)
            await session.flush()
            await session.refresh(schedule)
            session.expunge(schedule)
            await session.commit()
            return schedule

    async def list_schedules(self, org_id: str) -> list[ScheduleORM]:
        schedules, _ = await self.list_schedules_paginated(
            org_id,
            offset=0,
            limit=None,
        )
        return schedules

    async def list_schedules_paginated(
        self,
        org_id: str,
        *,
        offset: int = 0,
        limit: int | None = 50,
    ) -> tuple[list[ScheduleORM], int]:
        async with self.session_factory() as session:
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ScheduleORM)
                    .where(ScheduleORM.org_id == org_id)
                )
                or 0
            )
            stmt = (
                select(ScheduleORM)
                .where(ScheduleORM.org_id == org_id)
                .order_by(ScheduleORM.created_at.desc(), ScheduleORM.id.desc())
                .offset(offset)
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows), total

    async def get_schedule(
        self, schedule_id: str, org_id: str | None = None
    ) -> ScheduleORM | None:
        async with self.session_factory() as session:
            row = await session.get(ScheduleORM, schedule_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id:
                return None
            session.expunge(row)
            return row

    async def get_schedule_by_prefect_deployment_id(
        self,
        prefect_deployment_id: str,
        org_id: str,
    ) -> ScheduleORM | None:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(ScheduleORM)
                    .where(ScheduleORM.prefect_deployment_id == prefect_deployment_id)
                    .where(ScheduleORM.org_id == org_id)
                )
            ).scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    async def update_schedule(
        self,
        schedule_id: str,
        org_id: str,
        **kwargs: object,
    ) -> ScheduleORM | None:
        async with self.session_factory() as session:
            row = await session.get(ScheduleORM, schedule_id)
            if row is None or row.org_id != org_id:
                return None
            for key, value in kwargs.items():
                setattr(row, key, value)
            row.updated_at = _utcnow()
            await session.flush()
            await session.refresh(row)
            session.expunge(row)
            await session.commit()
            return row

    async def delete_schedule(self, schedule_id: str, org_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(ScheduleORM, schedule_id)
            if row is None or row.org_id != org_id:
                return False
            await session.delete(row)
            await session.commit()
            return True
