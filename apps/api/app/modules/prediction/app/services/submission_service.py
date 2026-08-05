from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from injector import inject

from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.datasets.port.local import validate_predictor_for_dataset
from app.modules.models.port.local import ModelCatalogPort
from app.modules.prediction.domain.submission import (
    PredictionJobCommand,
    PredictionResourceNotFoundError,
    PredictionRuntimeUnavailableError,
    PredictionSubmissionError,
    PredictionSubmissionRejectedError,
)
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.prediction.app.services.submission_parameters import (
    prediction_workflow_parameters,
)
from app.modules.runtime.port.local import RuntimeRoutingPort
from app.modules.runtime.catalog import runtime_catalog
from app.shared.api.schemas import JobStatus, PredictionEvent, PredictionJob
from app.shared.domain.protocols import PrefectClient


class PredictionSubmissionService:
    @inject
    def __init__(
        self,
        prefect_client: PrefectClient,
        repository: PredictionRepository,
        runtime_router: RuntimeRoutingPort,
        dataset_reader: DatasetReader,
        model_catalog: ModelCatalogPort,
    ) -> None:
        self._prefect_client = prefect_client
        self._repository = repository
        self._runtime_router = runtime_router
        self._dataset_reader = dataset_reader
        self._model_catalog = model_catalog

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
        dataset = await self._dataset_reader.get_dataset(
            command.dataset_id,
            org_id=command.org_id,
        )
        if dataset is None:
            raise PredictionResourceNotFoundError(
                f"Dataset '{command.dataset_id}' not found"
            )
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
        validate_predictor_for_dataset(
            predictor_id=predictor_id,
            view_types=dataset.view_types,
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
        try:
            route = self._runtime_router.prediction_route(predictor_id)
        except RuntimeError as exc:
            raise PredictionRuntimeUnavailableError(str(exc)) from exc
        deployment_id = await self._prefect_client.resolve_deployment_id(
            route.deployment
        )
        if deployment_id is None:
            raise PredictionRuntimeUnavailableError(
                f"Deployment '{route.deployment}' is not registered"
            )

        try:
            job = await self._repository.create_prediction_job(
                PredictionJob(
                    dataset_id=command.dataset_id,
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
                    route=route,
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

    async def _poll_run(self, job_id: str, external_id: str) -> None:
        last_log_count = 0
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
            logs = await self._prefect_client.get_flow_run_logs(external_id)
            for log in logs[last_log_count:]:
                await self._repository.add_prediction_event(
                    PredictionEvent(
                        job_id=job_id,
                        ts=datetime.now(UTC),
                        message=str(log.get("message", "")),
                        payload={"log_level": log.get("level", 0)},
                    )
                )
            last_log_count = len(logs)
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
