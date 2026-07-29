from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.shared.db.registry import SensorCheckpointORM, SensorSubscriptionORM
from app.modules.jobs.sensors.domain.entities.models import (
    SensorCheckpoint,
    SensorSubscription,
)


class SensorRepositoryImpl:
    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def list_subscriptions(self, sensor_id: str) -> list[SensorSubscription]:
        async with self._session_factory() as session:
            stmt = select(SensorSubscriptionORM).where(
                SensorSubscriptionORM.sensor_id == sensor_id
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._subscription_from_row(row) for row in rows]

    async def get_subscription(self, subscription_id: str) -> SensorSubscription | None:
        async with self._session_factory() as session:
            row = await session.get(SensorSubscriptionORM, subscription_id)
            if row is None:
                return None
            return self._subscription_from_row(row)

    async def create_subscription(
        self,
        sensor_id: str,
        workflow_type: str,
        filter_config: dict[str, Any],
        enabled: bool = True,
    ) -> SensorSubscription:
        async with self._session_factory() as session:
            row = SensorSubscriptionORM(
                sensor_id=sensor_id,
                workflow_type=workflow_type,
                filter_config=filter_config,
                enabled=enabled,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._subscription_from_row(row)

    async def update_subscription(
        self,
        subscription_id: str,
        *,
        filter_config: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> SensorSubscription | None:
        async with self._session_factory() as session:
            row = await session.get(SensorSubscriptionORM, subscription_id)
            if row is None:
                return None
            if filter_config is not None:
                row.filter_config = filter_config
            if enabled is not None:
                row.enabled = enabled
            await session.commit()
            await session.refresh(row)
            return self._subscription_from_row(row)

    async def delete_subscription(self, subscription_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(SensorSubscriptionORM, subscription_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def get_checkpoint(self, sensor_id: str) -> SensorCheckpoint | None:
        async with self._session_factory() as session:
            row = await session.get(SensorCheckpointORM, sensor_id)
            if row is None:
                return None
            return self._checkpoint_from_row(row)

    async def upsert_checkpoint(
        self, sensor_id: str, watermark: dict[str, Any]
    ) -> SensorCheckpoint:
        async with self._session_factory() as session:
            row = await session.merge(
                SensorCheckpointORM(sensor_id=sensor_id, watermark=watermark)
            )
            await session.commit()
            await session.refresh(row)
            return self._checkpoint_from_row(row)

    @staticmethod
    def _subscription_from_row(row: SensorSubscriptionORM) -> SensorSubscription:
        return SensorSubscription(
            id=row.id,
            sensor_id=row.sensor_id,
            workflow_type=row.workflow_type,
            filter_config=row.filter_config,
            enabled=row.enabled,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _checkpoint_from_row(row: SensorCheckpointORM) -> SensorCheckpoint:
        return SensorCheckpoint(
            sensor_id=row.sensor_id,
            watermark=row.watermark,
            updated_at=row.updated_at,
        )


SensorRepository = SensorRepositoryImpl
