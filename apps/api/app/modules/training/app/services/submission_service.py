from __future__ import annotations

import asyncio

from injector import inject

from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.dataset_collections.domain.errors import DatasetCollectionNotFoundError
from app.modules.dataset_collections.domain.models import DatasetCollectionRevision
from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.datasets.port.local import (
    validate_predictor_for_dataset,
    validate_trainer_for_dataset,
)
from app.modules.runtime.app.services.deployment_seed import (
    TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT,
)
from app.modules.runtime.catalog import runtime_catalog
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
from app.modules.training.domain.readiness import TrainingReadinessReport
from app.shared.application.artifacts import ArtifactService
from app.shared.api.schemas import Dataset, TrainingEvent, TrainingJob
from app.shared.api.schemas import JobStatus
from app.shared.domain.protocols import (
    NotificationSink,
    PrefectClient,
    TrainingExecutionEngine,
)


class TrainingSubmissionService:
    @inject
    def __init__(
        self,
        engine: TrainingExecutionEngine,
        notification_sink: NotificationSink,
        repository: TrainingRepository,
        artifact_service: ArtifactService,
        dataset_reader: DatasetReader,
        prefect_client: PrefectClient,
        readiness: TrainingReadinessService,
        collection_revisions: DatasetCollectionRevisionReaderPort,
    ) -> None:
        self.engine = engine
        self.notification_sink = notification_sink
        self.repository = repository
        self.artifact_service = artifact_service
        self._dataset_reader = dataset_reader
        self._prefect_client = prefect_client
        self._readiness = readiness
        self._collection_revisions = collection_revisions

    async def submit_job(self, command: TrainingJobCommand) -> TrainingJob:
        dataset, revision = await self._validate_source(
            command,
            trainer_id=command.trainer_id,
        )
        readiness_report = (
            await self._readiness.assess_classes(
                dataset=dataset,
                sample_ids=None,
                sample_filter=None,
            )
            if dataset is not None
            else self._revision_readiness(command, revision)
        )
        if not readiness_report.ready:
            raise TrainingReadinessError(readiness_report)
        return await self._start_job(
            TrainingJob(
                dataset_id=command.dataset_id,
                collection_id=command.collection_id,
                collection_revision_id=command.collection_revision_id,
                trainer_id=command.trainer_id,
                created_by=command.created_by,
                org_id=command.org_id,
            )
        )

    async def submit_train_and_predict(
        self,
        command: TrainAndPredictCommand,
    ) -> TrainAndPredictSubmission:
        dataset, revision = await self._validate_source(
            command,
            trainer_id=command.trainer_id,
        )
        predictor_id = runtime_catalog.resolve_predictor_id(
            command.trainer_id,
            requested_predictor_id=command.predictor_id,
        )
        if dataset is not None:
            validate_predictor_for_dataset(
                predictor_id=predictor_id,
                view_types=dataset.view_types,
            )
        else:
            assert revision is not None
            predictor = runtime_catalog.get_predictor_meta(predictor_id)
            if predictor.input_view.view_id != revision.target_view_id:
                raise ValueError(
                    f"Predictor '{predictor_id}' requires view "
                    f"'{predictor.input_view.view_id}', collection revision provides "
                    f"'{revision.target_view_id}'"
                )
        if command.sample_filter is not None and (
            dataset is None or dataset.dataset_type != "image_sc"
        ):
            raise ValueError("sample_filter is only supported for image_sc datasets")

        if not runtime_catalog.supports_train_and_predict(command.trainer_id):
            raise TrainingRuntimeUnavailableError(
                f"Trainer {command.trainer_id!r} does not support train-and-predict"
            )
        readiness_report = (
            await self._readiness.assess_classes(
                dataset=dataset,
                sample_ids=(
                    list(command.sample_ids) if command.sample_ids is not None else None
                ),
                sample_filter=command.sample_filter,
            )
            if dataset is not None
            else self._revision_readiness(
                command,
                revision,
            )
        )
        if not readiness_report.ready:
            raise TrainingReadinessError(readiness_report)

        deployment_id = await self._prefect_client.resolve_deployment_id(
            TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT.deployment_name
        )
        if deployment_id is None:
            raise TrainingRuntimeUnavailableError(
                "Deployment "
                f"'{TRAIN_AND_PREDICT_RUNTIME_DEPLOYMENT.deployment_name}' "
                "is not registered"
            )

        try:
            job = await self.repository.create_job(
                TrainingJob(
                    dataset_id=command.dataset_id,
                    collection_id=command.collection_id,
                    collection_revision_id=command.collection_revision_id,
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

    async def _validate_source(
        self,
        command: TrainingJobCommand,
        *,
        trainer_id: str,
    ) -> tuple[Dataset | None, DatasetCollectionRevision | None]:
        source = command.data_source
        if source.kind == "dataset":
            assert source.dataset_id is not None
            dataset = await self._dataset_reader.get_dataset(
                source.dataset_id,
                org_id=command.org_id,
            )
            if dataset is None:
                raise TrainingDatasetNotFoundError(source.dataset_id)
            validate_trainer_for_dataset(
                trainer_id=trainer_id,
                view_types=dataset.view_types,
            )
            return dataset, None
        assert source.collection_id is not None
        assert source.collection_revision_id is not None
        try:
            revision = await self._collection_revisions.get_revision(
                source.collection_id,
                source.collection_revision_id,
                command.org_id,
            )
        except DatasetCollectionNotFoundError as exc:
            raise TrainingDatasetNotFoundError(source.identity) from exc
        if revision.status != "ready" or revision.manifest_uri is None:
            raise ValueError(
                f"Collection revision '{revision.id}' is not ready for runtime use"
            )
        trainer = runtime_catalog.get_trainer_meta(trainer_id)
        if trainer.input_view.view_id != revision.target_view_id:
            raise ValueError(
                f"Trainer '{trainer_id}' requires view '{trainer.input_view.view_id}', "
                f"collection revision provides '{revision.target_view_id}'"
            )
        return None, revision

    @staticmethod
    def _revision_readiness(
        command: TrainingJobCommand,
        revision: DatasetCollectionRevision | None,
    ) -> TrainingReadinessReport:
        assert revision is not None
        active_labels = sorted(
            label for label, count in revision.label_counts.items() if count > 0
        )
        reasons = (
            ()
            if len(active_labels) >= 2
            else (f"training requires at least 2 active labels; got {active_labels}",)
        )
        annotated = sum(revision.label_counts.values())
        return TrainingReadinessReport(
            dataset_id=command.data_source.identity,
            annotated_samples=annotated,
            readable_samples=annotated,
            runtime_resolvable_samples=0,
            unusable_samples=0,
            skipped_samples=0,
            label_counts=dict(revision.label_counts),
            failure_reasons=reasons,
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
