from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from injector import inject

from app.modules.dataset_collections.domain.errors import DatasetCollectionNotFoundError
from app.modules.dataset_collections.domain.models import DatasetCollectionRevision
from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.datasets.domain.entities import DatasetRevision
from app.modules.datasets.port.local import (
    DatasetRevisionReaderPort,
    validate_predictor_for_dataset,
)
from app.modules.models.port.local import ModelCatalogPort
from app.modules.prediction.domain.submission import (
    PredictionJobCommand,
    PredictionResourceNotFoundError,
    PredictionRuntimeUnavailableError,
    PredictionSubmissionError,
    PredictionSubmissionRejectedError,
    PredictionSubmissionOrigin,
)
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.prediction.app.services.submission_parameters import (
    prediction_workflow_parameters,
)
from app.modules.runtime.app.services.deployment_catalog import (
    PREDICTION_AUTOMATION_RUNTIME_DEPLOYMENT,
    PREDICTION_RUNTIME_DEPLOYMENT,
)
from app.modules.runtime.catalog import runtime_catalog
from app.shared.api.schemas import JobStatus, PredictionEvent, PredictionJob
from app.shared.api.schemas import Dataset
from app.shared.domain.protocols import PrefectClient

_LOG_PAGE_SIZE = 200


class PredictionSubmissionService:
    @inject
    def __init__(
        self,
        prefect_client: PrefectClient,
        repository: PredictionRepository,
        dataset_reader: DatasetReader,
        model_catalog: ModelCatalogPort,
        dataset_revisions: DatasetRevisionReaderPort,
        collection_revisions: DatasetCollectionRevisionReaderPort | None = None,
    ) -> None:
        self._prefect_client = prefect_client
        self._repository = repository
        self._dataset_reader = dataset_reader
        self._model_catalog = model_catalog
        self._dataset_revisions = dataset_revisions
        self._collection_revisions = collection_revisions

    @staticmethod
    def _extract_summary_from_run(run: dict | None) -> dict:
        if not isinstance(run, dict):
            return {}

        state = run.get("state", {})
        if not isinstance(state, dict):
            return {}

        data = state.get("data")
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {}
        if data is not None and hasattr(data, "model_dump"):
            dumped = data.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        if data is not None and hasattr(data, "dict"):
            dumped = data.dict()
            return dumped if isinstance(dumped, dict) else {}
        return {}

    async def submit_job(self, command: PredictionJobCommand) -> PredictionJob:
        dataset, revision, dataset_revision = await self._resolve_source(command)
        model = await self._model_catalog.get_model(
            command.model_id,
            org_id=command.org_id,
        )
        if model is None:
            raise PredictionResourceNotFoundError(
                f"Model '{command.model_id}' not found"
            )
        trainer_id = model.trainer_id or model.trainer_name or ""
        if not trainer_id:
            raise PredictionSubmissionRejectedError(
                f"Model '{command.model_id}' has no associated predictor"
            )
        try:
            predictor_id = runtime_catalog.resolve_predictor_id(
                trainer_id,
                requested_predictor_id=command.predictor_id,
            )
        except (KeyError, ValueError) as exc:
            raise PredictionSubmissionRejectedError(str(exc)) from exc
        if dataset is not None:
            validate_predictor_for_dataset(
                predictor_id=predictor_id,
                view_types=dataset.view_types,
            )
        else:
            assert revision is not None
            predictor = runtime_catalog.get_predictor_meta(predictor_id)
            if predictor.input_view.view_id != revision.target_view_id:
                raise PredictionSubmissionRejectedError(
                    f"Predictor '{predictor_id}' requires view "
                    f"'{predictor.input_view.view_id}', collection revision provides "
                    f"'{revision.target_view_id}'"
                )
        model_metadata = model.metadata if isinstance(model.metadata, dict) else {}
        try:
            runtime_catalog.validate_predictor_model_contract(
                predictor_id,
                model_contract=model_metadata.get("model_contract"),
                model_schema_version=model_metadata.get("model_schema_version"),
            )
        except ValueError as exc:
            raise PredictionSubmissionRejectedError(
                f"Model '{command.model_id}' cannot use predictor "
                f"'{predictor_id}': {exc}"
            ) from exc
        deployment = (
            PREDICTION_AUTOMATION_RUNTIME_DEPLOYMENT
            if command.submission_origin is PredictionSubmissionOrigin.AUTOMATION
            else PREDICTION_RUNTIME_DEPLOYMENT
        )
        deployment_id = await self._prefect_client.resolve_deployment_id(
            deployment.deployment_name
        )
        if deployment_id is None:
            raise PredictionRuntimeUnavailableError(
                f"Deployment '{deployment.deployment_name}' is not registered"
            )

        try:
            job = await self._repository.create_prediction_job(
                PredictionJob(
                    dataset_id=command.dataset_id,
                    dataset_revision_id=(
                        dataset_revision.id if dataset_revision is not None else None
                    ),
                    collection_id=command.collection_id,
                    collection_revision_id=command.collection_revision_id,
                    model_id=command.model_id,
                    created_by=command.created_by,
                    target=command.target,
                    model_version=command.model_version,
                    org_id=command.org_id,
                    sample_ids=(
                        list(command.sample_ids)
                        if command.sample_ids is not None
                        else None
                    ),
                    summary={
                        "predictor_id": predictor_id,
                        "submission_origin": command.submission_origin.value,
                        **(
                            {
                                "collection_prediction_batch_id": (
                                    command.collection_prediction_batch_id
                                )
                            }
                            if command.collection_prediction_batch_id is not None
                            else {}
                        ),
                        **(
                            {"collection_member_id": command.collection_member_id}
                            if command.collection_member_id is not None
                            else {}
                        ),
                        **(
                            {"prompt": command.prompt}
                            if command.prompt is not None
                            else {}
                        ),
                    },
                ),
                org_id=command.org_id,
            )
        except Exception as exc:
            raise PredictionSubmissionError(
                f"Failed to persist prediction job: {exc}"
            ) from exc
        try:
            run = await self._prefect_client.create_flow_run_from_deployment(
                deployment_id=deployment_id,
                parameters=prediction_workflow_parameters(
                    command,
                    job_id=job.id,
                    predictor_id=predictor_id,
                ),
                idempotency_key=job.id,
            )
        except Exception as exc:
            await self._repository.update_prediction_job_status(
                job.id,
                JobStatus.FAILED,
                summary={"submission_error": str(exc)},
            )
            raise PredictionSubmissionError(
                f"Failed to start prediction workflow: {exc}"
            ) from exc
        external_id = str(run["id"])
        await self._repository.set_prediction_job_external_id(job.id, external_id)
        start_event = PredictionEvent(
            job_id=job.id,
            ts=datetime.now(UTC),
            message="prediction job submitted",
            payload={"external_id": external_id, "status": JobStatus.QUEUED.value},
        )
        await self._repository.add_prediction_event(start_event)
        asyncio.create_task(self._poll_run(job.id, external_id))
        return (
            await self._repository.get_prediction_job(job.id, org_id=job.org_id)
        ) or job

    async def _resolve_source(
        self, command: PredictionJobCommand
    ) -> tuple[
        Dataset | None,
        DatasetCollectionRevision | None,
        DatasetRevision | None,
    ]:
        source = command.data_source
        if source.kind == "dataset":
            assert source.dataset_id is not None
            dataset = await self._dataset_reader.get_dataset(
                source.dataset_id,
                org_id=command.org_id,
            )
            if dataset is None:
                raise PredictionResourceNotFoundError(
                    f"Dataset '{source.dataset_id}' not found"
                )
            dataset_revision = await self._dataset_revisions.resolve_or_create_baseline(
                dataset_id=source.dataset_id,
                org_id=command.org_id,
                created_by=command.created_by,
            )
            return dataset, None, dataset_revision
        assert source.collection_id is not None
        assert source.collection_revision_id is not None
        if self._collection_revisions is None:
            raise PredictionRuntimeUnavailableError(
                "Collection revision reader is not configured"
            )
        try:
            revision = await self._collection_revisions.get_revision(
                source.collection_id,
                source.collection_revision_id,
                command.org_id,
            )
        except DatasetCollectionNotFoundError as exc:
            raise PredictionResourceNotFoundError(
                f"Collection revision '{source.identity}' not found"
            ) from exc
        if revision.status != "ready" or revision.manifest_uri is None:
            raise PredictionSubmissionRejectedError(
                f"Collection revision '{revision.id}' is not ready for runtime use"
            )
        return None, revision, None

    async def _poll_run(self, job_id: str, external_id: str) -> None:
        log_offset = 0
        previous_state = ""
        while True:
            await asyncio.sleep(2)
            run = await self._prefect_client.get_flow_run(external_id)
            state = str(run.get("state", {}).get("type", ""))
            if state and state != previous_state:
                await self._repository.add_prediction_event(
                    PredictionEvent(
                        job_id=job_id,
                        ts=datetime.now(UTC),
                        message=f"prefect state: {state}",
                        payload={"prefect_state": state},
                    )
                )
                if state == "RUNNING":
                    await self._repository.update_prediction_job_status(
                        job_id, JobStatus.RUNNING
                    )
                elif state in {"SCHEDULED", "PENDING"}:
                    await self._repository.update_prediction_job_status(
                        job_id, JobStatus.QUEUED
                    )
                previous_state = state
            while True:
                logs = await self._prefect_client.get_flow_run_logs(
                    external_id,
                    limit=_LOG_PAGE_SIZE,
                    offset=log_offset,
                )
                for log in logs:
                    await self._repository.add_prediction_event(
                        PredictionEvent(
                            job_id=job_id,
                            ts=datetime.now(UTC),
                            message=str(log.get("message", "")),
                            payload={"log_level": log.get("level", 0)},
                        )
                    )
                log_offset += len(logs)
                if len(logs) < _LOG_PAGE_SIZE:
                    break
            if state in {"COMPLETED", "FAILED", "CANCELLED", "CRASHED"}:
                break

        run = await self._prefect_client.get_flow_run(external_id)
        state = str(run.get("state", {}).get("type", "FAILED"))
        summary = self._extract_summary_from_run(run)
        if not summary:
            existing_job = await self._repository.get_prediction_job(job_id)
            if existing_job is not None and isinstance(existing_job.summary, dict):
                summary = existing_job.summary
        if state == "COMPLETED":
            await self._repository.update_prediction_job_status(
                job_id, JobStatus.COMPLETED, summary=summary
            )
            status = "completed"
        elif state == "CANCELLED":
            await self._repository.update_prediction_job_status(
                job_id, JobStatus.CANCELLED, summary=summary
            )
            status = "cancelled"
        else:
            await self._repository.update_prediction_job_status(
                job_id, JobStatus.FAILED, summary=summary
            )
            status = "failed"
        await self._repository.add_prediction_event(
            PredictionEvent(
                job_id=job_id,
                ts=datetime.now(UTC),
                message=f"prediction {status}",
                payload={"status": status, "summary": summary},
            )
        )

    async def cancel_job(self, job_id: str, org_id: str | None = None) -> bool:
        job = await self._repository.get_prediction_job(job_id, org_id=org_id)
        if job is None or not job.external_job_id:
            return False
        await self._prefect_client.set_flow_run_state(job.external_job_id, "CANCELLING")
        await self._repository.update_prediction_job_status(job_id, JobStatus.CANCELLED)
        await self._repository.add_prediction_event(
            PredictionEvent(
                job_id=job_id,
                ts=datetime.now(UTC),
                message="prediction cancellation requested",
                payload={"external_id": job.external_job_id},
            )
        )
        return True
