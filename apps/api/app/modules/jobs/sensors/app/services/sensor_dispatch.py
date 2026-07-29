from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.modules.jobs.sensors.domain.repository import SensorRepository
from app.shared.domain.protocols import PrefectClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DispatchSummary:
    matched: int
    triggered: int
    errors: int


class SensorDispatchService:
    def __init__(
        self, repository: SensorRepository, prefect_client: PrefectClient
    ) -> None:
        self._repo = repository
        self._prefect_client = prefect_client

    async def dispatch(
        self, sensor_id: str, events: list[dict[str, Any]]
    ) -> DispatchSummary:
        matched = 0
        triggered = 0
        errors = 0

        subscriptions = await self._repo.list_subscriptions(sensor_id)
        for subscription in subscriptions:
            if not subscription.enabled:
                continue
            try:
                deployment_id = await self._prefect_client.resolve_deployment_id(
                    subscription.workflow_type
                )
                if deployment_id is None:
                    logger.warning(
                        "No Prefect deployment found for sensor subscription %s workflow_type %s",
                        subscription.id,
                        subscription.workflow_type,
                    )
                    continue
                matching_events = [
                    event
                    for event in events
                    if self._matches_filter(event, subscription.filter_config)
                ]
                matched += len(matching_events)
                for event in matching_events:
                    await self._prefect_client.create_flow_run_from_deployment(
                        deployment_id,
                        {"event": event, "subscription_id": str(subscription.id)},
                    )
                    triggered += 1
            except Exception:
                errors += 1
                logger.exception(
                    "Failed to dispatch sensor subscription %s for sensor %s",
                    subscription.id,
                    sensor_id,
                )

        return DispatchSummary(matched=matched, triggered=triggered, errors=errors)

    @staticmethod
    def _matches_filter(event: dict[str, Any], filter_config: dict[str, Any]) -> bool:
        return all(event.get(key) == value for key, value in filter_config.items())
