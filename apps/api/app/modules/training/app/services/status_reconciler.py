from __future__ import annotations

import asyncio
import logging

from app.modules.training.domain.repository import TrainingRepository
from app.shared.api.schemas import JobStatus, TrainingEvent
from app.shared.domain.protocols import NotificationSink, TrainingExecutionEngine

_logger = logging.getLogger(__name__)


class TrainingStatusReconciler:
    """Keep durable platform job status aligned with the execution backend."""

    def __init__(
        self,
        *,
        engine: TrainingExecutionEngine,
        repository: TrainingRepository,
        notification_sink: NotificationSink,
        interval_seconds: float,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("training status reconcile interval must be positive")
        self._engine = engine
        self._repository = repository
        self._notification_sink = notification_sink
        self._interval_seconds = interval_seconds
        self._wake = asyncio.Event()
        self._stopping = False
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(
            self._run(),
            name="training-status-reconciler",
        )

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._stopping = True
        self._wake.set()
        await task
        self._task = None

    def wake(self) -> None:
        self._wake.set()

    async def reconcile_once(self) -> None:
        executions = await self._repository.list_active_executions()
        for execution in executions:
            try:
                status = await self._engine.status(execution.external_job_id)
            except Exception:
                _logger.warning(
                    "Failed to reconcile training job %s",
                    execution.job_id,
                    exc_info=True,
                )
                continue
            if status == execution.status:
                continue
            changed = await self._repository.update_job_status(
                execution.job_id,
                status,
            )
            if not changed:
                continue
            event = TrainingEvent(
                job_id=execution.job_id,
                message=f"training status reconciled: {status.value}",
                payload={
                    "status": status.value,
                    "source": "execution_reconciler",
                },
            )
            await self._repository.add_event(event)
            if status in {
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }:
                self._notification_sink.notify_job_terminal(event)
            else:
                self._notification_sink.notify_job_update(event)

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.reconcile_once()
            except Exception:
                _logger.exception("Training status reconciliation pass failed")
            if self._stopping:
                break
            self._wake.clear()
            try:
                await asyncio.wait_for(
                    self._wake.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass
