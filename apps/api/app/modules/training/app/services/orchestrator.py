from __future__ import annotations

import asyncio
from typing import cast

from app.modules.training.domain.repository import TrainingRepository
from app.shared.application.artifacts import ArtifactService
from app.shared.api.schemas import TrainingEvent, TrainingJob
from app.shared.api.schemas import JobStatus
from app.shared.domain.protocols import NotificationSink, TrainingExecutionEngine


class TrainingOrchestrator:
    def __init__(
        self,
        engine: TrainingExecutionEngine | object,
        notification_sink: NotificationSink | object,
        repository: TrainingRepository | object,
        artifact_service: ArtifactService,
    ) -> None:
        self.engine = cast(TrainingExecutionEngine, engine)
        self.notification_sink = cast(NotificationSink, notification_sink)
        self.repository = cast(TrainingRepository, repository)
        self.artifact_service = artifact_service

    async def start_job(self, job: TrainingJob) -> TrainingJob:
        await self.repository.create_job(job)
        external_id = await self.engine.submit(job)
        await self.repository.set_job_external_id(job.id, external_id)
        queued_event = TrainingEvent(
            job_id=job.id,
            message="job submitted",
            payload={"external_id": external_id, "status": JobStatus.QUEUED.value},
        )
        await self.repository.add_event(queued_event)
        self.notification_sink.notify_job_update(queued_event)

        asyncio.create_task(self._run_job(job.id, external_id))

        return job

    async def _run_job(self, job_id: str, external_id: str) -> None:
        terminal_status = None
        terminal_event = None
        async for event in self.engine.stream_events(external_id):
            await self.repository.add_event(event)
            self.notification_sink.notify_job_update(event)
            prefect_state = event.payload.get("prefect_state")
            if prefect_state == "RUNNING":
                await self.repository.update_job_status(job_id, JobStatus.RUNNING)
            elif prefect_state in ("SCHEDULED", "PENDING"):
                await self.repository.update_job_status(job_id, JobStatus.QUEUED)
            status_val = event.payload.get("status")
            if status_val in ("completed", "failed", "cancelled"):
                terminal_status = status_val
                terminal_event = event

        if terminal_event is not None:
            if terminal_status == "completed":
                artifacts = await self.engine.collect_artifacts(external_id)
                if not artifacts:
                    job = await self.repository.get_job(job_id)
                    artifacts = list(job.artifact_refs) if job is not None else []
                if not artifacts:
                    await self.repository.update_job_status(job_id, JobStatus.FAILED)
                    failure_event = TrainingEvent(
                        job_id=job_id,
                        message="training failed: execution completed without artifacts",
                        payload={"status": "failed", "reason": "missing_artifacts"},
                    )
                    await self.repository.add_event(failure_event)
                    self.notification_sink.notify_job_update(failure_event)
                    terminal_event = failure_event
                    terminal_status = "failed"
                else:
                    await self.repository.update_job_status(job_id, JobStatus.COMPLETED)
                    job = await self.repository.get_job(job_id)
                    existing_artifact_ids = {
                        artifact.id
                        for artifact in (job.artifact_refs if job is not None else [])
                    }
                    new_artifacts = [
                        artifact
                        for artifact in artifacts
                        if artifact.id not in existing_artifact_ids
                    ]
                    if new_artifacts:
                        await self.artifact_service.persist_job_artifacts(
                            job_id, new_artifacts
                        )
            elif terminal_status == "failed":
                await self.repository.update_job_status(job_id, JobStatus.FAILED)
            elif terminal_status == "cancelled":
                await self.repository.update_job_status(job_id, JobStatus.CANCELLED)
            self.notification_sink.notify_job_terminal(terminal_event)
            if await self.repository.did_user_leave(job_id):
                self.notification_sink.notify_user_left_and_complete(terminal_event)

    async def cancel_job(self, job_id: str) -> bool:
        ext = await self.repository.get_job_external_id(job_id)
        if not ext:
            return False
        ok = await self.engine.cancel(ext)
        if ok:
            await self.repository.update_job_status(job_id, JobStatus.CANCELLED)
        return ok
