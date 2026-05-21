from __future__ import annotations

import httpx

from app.domain.models import TrainingEvent


class WebhookNotificationSink:
    def __init__(self, endpoint: str, timeout_seconds: int = 5) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def _post(self, event_type: str, event: TrainingEvent) -> None:
        payload = {
            "event_type": event_type,
            "job_id": event.job_id,
            "message": event.message,
            "payload": event.payload,
            "ts": event.ts.isoformat(),
        }
        try:
            httpx.post(self.endpoint, json=payload, timeout=self.timeout_seconds)
        except Exception:
            return

    def notify_job_update(self, event: TrainingEvent) -> None:
        self._post("job_update", event)

    def notify_job_terminal(self, event: TrainingEvent) -> None:
        self._post("job_terminal", event)

    def notify_user_left_and_complete(self, event: TrainingEvent) -> None:
        self._post("user_left_and_complete", event)
