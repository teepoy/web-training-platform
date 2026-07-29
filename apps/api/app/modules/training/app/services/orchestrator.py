from __future__ import annotations

import asyncio

from injector import inject

from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.datasets.port.local import (
    validate_predictor_for_dataset,
    validate_trainer_for_dataset,
)
from app.modules.runtime.port.local import RuntimeRoutingPort
from app.modules.types import catalog
from app.modules.training.app.services.readiness import TrainingReadinessService
from app.modules.training.app.services.submission_parameters import (
    train_and_predict_workflow_parameters,
)
from app.modules.training.domain.submission import (
    TrainAndPredictCommand,
    TrainAndPredictSubmission,
    TrainingDatasetNotFoundError,
    TrainingJobCommand,
    TrainingReadinessError,
    TrainingRuntimeUnavailableError,
    TrainingSubmissionError,
)
from app.modules.training.domain.repository import TrainingRepository
from app.shared.application.artifacts import ArtifactService
from app.shared.api.schemas import TrainingEvent, TrainingJob
from app.shared.api.schemas import JobStatus
from app.shared.domain.protocols import (
    NotificationSink,
    PrefectClient,
    TrainingExecutionEngine,
)


class TrainingOrchestrator:
    @inject
    def __init__(
        self,
        engine: TrainingExecutionEngine,
        notification_sink: NotificationSink,
        repository: TrainingRepository,
        artifact_service: ArtifactService,
        dataset_reader: DatasetReader,
        prefect_client: PrefectClient,
        runtime_router: RuntimeRoutingPort,
        readiness: TrainingReadinessService,
    ) -> None:
        self.engine = engine
        self.notification_sink = notification_sink
        self.repository = repository
        self.artifact_service = artifact_service
        self._dataset_reader = dataset_reader
        self._prefect_client = prefect_client
        self._runtime_router = runtime_router
        self._readiness = readiness

    async def submit_job(self, command: TrainingJobCommand) -> TrainingJob:
        dataset = await self._dataset_reader.get_dataset(
            command.dataset_id,
            org_id=command.org_id,
        )
        if dataset is None:
            raise TrainingDatasetNotFoundError(command.dataset_id)
        validate_trainer_for_dataset(
            trainer_id=command.trainer_id,
            view_types=dataset.view_types,
        )
        return await self._start_job(
            TrainingJob(
                dataset_id=command.dataset_id,
                trainer_id=command.trainer_id,
                created_by=command.created_by,
                org_id=command.org_id,
            )
        )

    async def submit_train_and_predict(
        self,
        command: TrainAndPredictCommand,
    ) -> TrainAndPredictSubmission:
        dataset = await self._dataset_reader.get_dataset(
            command.dataset_id,
            org_id=command.org_id,
        )
        if dataset is None:
            raise TrainingDatasetNotFoundError(command.dataset_id)
        validate_trainer_for_dataset(
            trainer_id=command.trainer_id,
            view_types=dataset.view_types,
        )
        predictor_id = catalog.resolve_predictor_id(
            command.trainer_id,
            requested_predictor_id=command.predictor_id,
        )
        validate_predictor_for_dataset(
            predictor_id=predictor_id,
            view_types=dataset.view_types,
        )
        if command.sample_filter is not None and dataset.dataset_type != "image_sc":
            raise ValueError("sample_filter is only supported for image_sc datasets")

        try:
            route = self._runtime_router.train_and_predict_route(command.trainer_id)
        except RuntimeError as exc:
            raise TrainingRuntimeUnavailableError(str(exc)) from exc
        readiness_report = await self._readiness.assess(
            dataset=dataset,
            sample_ids=(
                list(command.sample_ids) if command.sample_ids is not None else None
            ),
            sample_filter=command.sample_filter,
            missing_image_policy=route.missing_image_policy,
        )
        if not readiness_report.ready:
            raise TrainingReadinessError(readiness_report)

        deployment_id = await self._prefect_client.resolve_deployment_id(
            route.deployment
        )
        if deployment_id is None:
            raise TrainingRuntimeUnavailableError(
                f"Deployment '{route.deployment}' is not registered"
            )

        try:
            job = await self.repository.create_job(
                TrainingJob(
                    dataset_id=command.dataset_id,
                    trainer_id=command.trainer_id,
                    created_by=command.created_by,
                    org_id=command.org_id,
                )
            )
        except Exception as exc:
            raise TrainingSubmissionError(
                f"Failed to persist training job: {exc}"
            ) from exc
        try:
            run = await self._prefect_client.create_flow_run_from_deployment(
                deployment_id=deployment_id,
                parameters=train_and_predict_workflow_parameters(
                    command,
                    job_id=job.id,
                    route=route,
                ),
                idempotency_key=f"train-and-predict:{job.id}",
            )
        except Exception as exc:
            await self.repository.update_job_status(job.id, JobStatus.FAILED)
            raise TrainingSubmissionError(
                f"Failed to start train and predict workflow: {exc}"
            ) from exc

        workflow_run_id = str(run["id"])
        await self.repository.set_job_external_id(job.id, workflow_run_id)
        await self.repository.add_event(
            TrainingEvent(
                job_id=job.id,
                message="train and predict workflow submitted",
                payload={
                    "external_id": workflow_run_id,
                    "status": JobStatus.QUEUED.value,
                    **(
                        {"sample_filter": command.sample_filter}
                        if command.sample_filter is not None
                        else {}
                    ),
                },
            )
        )
        job.external_job_id = workflow_run_id
        return TrainAndPredictSubmission(
            train_job=job,
            workflow_run_id=workflow_run_id,
        )

    async def _start_job(self, job: TrainingJob) -> TrainingJob:
        try:
            job = await self.repository.create_job(job)
        except Exception as exc:
            raise TrainingSubmissionError(
                f"Failed to persist training job: {exc}"
            ) from exc
        try:
            external_id = await self.engine.submit(job)
        except Exception as exc:
            await self.repository.update_job_status(job.id, JobStatus.FAILED)
            raise TrainingSubmissionError(
                f"Failed to submit training job: {exc}"
            ) from exc
        await self.repository.set_job_external_id(job.id, external_id)
        queued_event = TrainingEvent(
            job_id=job.id,
            message="job submitted",
            payload={"external_id": external_id, "status": JobStatus.QUEUED.value},
        )
        await self.repository.add_event(queued_event)
        self.notification_sink.notify_job_update(queued_event)

        asyncio.create_task(self._run_job(job.id, external_id))

        job.external_job_id = external_id
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
