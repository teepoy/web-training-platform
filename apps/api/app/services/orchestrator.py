from __future__ import annotations

import asyncio

from app.domain.models import TrainingEvent, TrainingJob
from app.domain.types import JobStatus


class TrainingOrchestrator:
    def __init__(self, engine, notification_sink, repository, artifact_service) -> None:
        self.engine = engine
        self.notification_sink = notification_sink
        self.repository = repository
        self.artifact_service = artifact_service

    async def start_job(self, job: TrainingJob) -> TrainingJob:
        await self.repository.create_job(job)
        external_id = await self.engine.submit(job)
        await self.repository.set_job_external_id(job.id, external_id)
        job.status = JobStatus.RUNNING
        await self.repository.update_job_status(job.id, JobStatus.RUNNING)
        queued_event = TrainingEvent(job_id=job.id, message="job started", payload={"external_id": external_id})
        await self.repository.add_event(queued_event)
        self.notification_sink.notify_job_update(queued_event)

        asyncio.create_task(self._run_job(job.id, external_id))

        return job

    async def _run_job(self, job_id: str, external_id: str) -> None:
        terminal = None
        async for event in self.engine.stream_events(external_id):
            await self.repository.add_event(event)
            self.notification_sink.notify_job_update(event)
            if event.payload.get("status") == "completed":
                terminal = event

        if terminal is not None:
            await self.repository.update_job_status(job_id, JobStatus.COMPLETED)
            artifacts = await self.engine.collect_artifacts(external_id)
            await self.artifact_service.persist_job_artifacts(job_id, artifacts)
            self.notification_sink.notify_job_terminal(terminal)
            if await self.repository.did_user_leave(job_id):
                self.notification_sink.notify_user_left_and_complete(terminal)

    async def cancel_job(self, job_id: str) -> bool:
        ext = await self.repository.get_job_external_id(job_id)
        if not ext:
            return False
        ok = await self.engine.cancel(ext)
        if ok:
            await self.repository.update_job_status(job_id, JobStatus.CANCELLED)
        return ok
