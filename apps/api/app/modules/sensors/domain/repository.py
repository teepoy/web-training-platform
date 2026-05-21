from __future__ import annotations

from typing import Any, Protocol

from app.modules.sensors.domain.entities.models import (
    SensorCheckpoint,
    SensorSubscription,
)


class SensorRepository(Protocol):
    async def list_subscriptions(self, sensor_id: str) -> list[SensorSubscription]: ...

    async def get_subscription(
        self, subscription_id: str
    ) -> SensorSubscription | None: ...

    async def create_subscription(
        self,
        sensor_id: str,
        workflow_type: str,
        filter_config: dict[str, Any],
        enabled: bool = True,
    ) -> SensorSubscription: ...

    async def update_subscription(
        self,
        subscription_id: str,
        *,
        filter_config: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> SensorSubscription | None: ...

    async def delete_subscription(self, subscription_id: str) -> bool: ...

    async def upsert_checkpoint(
        self, sensor_id: str, watermark: dict[str, Any]
    ) -> SensorCheckpoint: ...
