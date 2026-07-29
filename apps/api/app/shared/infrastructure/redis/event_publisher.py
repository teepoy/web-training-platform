from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol

_logger = logging.getLogger(__name__)


class _RedisPubSubClient(Protocol):
    """Minimal protocol for the redis.asyncio.Redis client used for pub/sub."""

    async def publish(self, channel: str, message: str) -> int: ...

    async def aclose(self) -> None: ...


ANNOTATION_CHANNEL = "finetune:events:annotation"
PREDICTION_CHANNEL = "finetune:events:prediction"

ANNOTATION_CREATED = "annotation.created"
ANNOTATION_UPDATED = "annotation.updated"
ANNOTATION_DELETED = "annotation.deleted"
PREDICTION_CREATED = "prediction.created"
PREDICTION_UPDATED = "prediction.updated"
PREDICTION_REFRESH = "prediction.refresh"


class RedisEventPublisher:
    def __init__(self, redis_client: _RedisPubSubClient | None) -> None:
        self._redis = redis_client

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def _publish(
        self, channel: str, event_type: str, data: dict[str, Any]
    ) -> None:
        if self._redis is None:
            return
        payload = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        try:
            await self._redis.publish(channel, json.dumps(payload))
        except Exception:
            _logger.warning(
                "Failed to publish event %s to channel %s",
                event_type,
                channel,
                exc_info=True,
            )

    async def publish_annotation_created(
        self, *, annotation_id: str, sample_id: str, dataset_id: str
    ) -> None:
        await self._publish(
            ANNOTATION_CHANNEL,
            ANNOTATION_CREATED,
            {
                "annotation_id": annotation_id,
                "sample_id": sample_id,
                "dataset_id": dataset_id,
            },
        )

    async def publish_annotation_updated(
        self, *, annotation_id: str, sample_id: str, dataset_id: str
    ) -> None:
        await self._publish(
            ANNOTATION_CHANNEL,
            ANNOTATION_UPDATED,
            {
                "annotation_id": annotation_id,
                "sample_id": sample_id,
                "dataset_id": dataset_id,
            },
        )

    async def publish_annotation_deleted(
        self, *, annotation_id: str, sample_id: str, dataset_id: str
    ) -> None:
        await self._publish(
            ANNOTATION_CHANNEL,
            ANNOTATION_DELETED,
            {
                "annotation_id": annotation_id,
                "sample_id": sample_id,
                "dataset_id": dataset_id,
            },
        )

    # FIXME: dead code — never called by any endpoint or flow.
    # Prediction CRUD endpoints do not yet publish events.
    # See tests/test_pubsub_events.py::TestPredictionDeadCode.
    async def publish_prediction_created(
        self, *, prediction_id: str, sample_id: str, dataset_id: str
    ) -> None:
        await self._publish(
            PREDICTION_CHANNEL,
            PREDICTION_CREATED,
            {
                "prediction_id": prediction_id,
                "sample_id": sample_id,
                "dataset_id": dataset_id,
            },
        )

    # FIXME: dead code — never called by any endpoint or flow.
    # Prediction CRUD endpoints do not yet publish events.
    # See tests/test_pubsub_events.py::TestPredictionDeadCode.
    async def publish_prediction_updated(
        self, *, prediction_id: str, sample_id: str, dataset_id: str
    ) -> None:
        await self._publish(
            PREDICTION_CHANNEL,
            PREDICTION_UPDATED,
            {
                "prediction_id": prediction_id,
                "sample_id": sample_id,
                "dataset_id": dataset_id,
            },
        )

    async def publish_prediction_refresh(self, *, dataset_id: str, job_id: str) -> None:
        await self._publish(
            PREDICTION_CHANNEL,
            PREDICTION_REFRESH,
            {
                "dataset_id": dataset_id,
                "job_id": job_id,
            },
        )

    async def publish_annotation_refresh(self, *, dataset_id: str) -> None:
        await self._publish(
            ANNOTATION_CHANNEL,
            ANNOTATION_UPDATED,
            {
                "dataset_id": dataset_id,
            },
        )
