from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.domain.models import PredictionEvent, PredictionJob
from app.domain.types import JobStatus


class PredictionOrchestrator:
    def __init__(self, prefect_client, repository) -> None:
        self._prefect_client = prefect_client
        self._repository = repository

    @staticmethod
    def _deployment_name_for_target(target: str) -> str:
        if target == "embedding":
            return "embed-job-batch-deployment"
        return "predict-job-batch-deployment"

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
        if hasattr(data, "model_dump"):
            dumped = data.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        if hasattr(data, "dict"):
            dumped = data.dict()
            return dumped if isinstance(dumped, dict) else {}
        return {}

    async def start_job(self, job: PredictionJob) -> PredictionJob:
        await self._repository.create_prediction_job(job)
        deployment_name = self._deployment_name_for_target(str(job.target))
        deployment_id = await self._prefect_client.resolve_deployment_id(deployment_name)
        if deployment_id is None:
            raise ValueError(f"Prediction deployment is not registered: {deployment_name}")
        run = await self._prefect_client.create_flow_run_from_deployment(
            deployment_id=deployment_id,
            parameters={
                "job_id": job.id,
                "dataset_id": job.dataset_id,
                "model_id": job.model_id,
                "org_id": job.org_id,
                "created_by": job.created_by,
                "target": job.target,
                "model_version": job.model_version,
                "sample_ids": job.sample_ids,
                "prompt": (
                    job.summary.get("prompt")
                    if isinstance(job.summary, dict) and job.summary.get("prompt") is not None
                    else (job.summary.get("embed_model") if isinstance(job.summary, dict) else None)
                ),
            },
            idempotency_key=job.id,
        )
        external_id = run["id"]
        await self._repository.set_prediction_job_external_id(job.id, external_id)
        await self._repository.update_prediction_job_status(job.id, JobStatus.RUNNING)
        start_event = PredictionEvent(
            job_id=job.id,
            ts=datetime.now(UTC),
            message="prediction job started",
            payload={"external_id": external_id},
        )
        await self._repository.add_prediction_event(start_event)
        asyncio.create_task(self._poll_run(job.id, external_id))
        return (await self._repository.get_prediction_job(job.id, org_id=job.org_id)) or job

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
            await self._repository.update_prediction_job_status(job_id, JobStatus.COMPLETED, summary=summary)
            status = "completed"
        elif state == "CANCELLED":
            await self._repository.update_prediction_job_status(job_id, JobStatus.CANCELLED, summary=summary)
            status = "cancelled"
        else:
            await self._repository.update_prediction_job_status(job_id, JobStatus.FAILED, summary=summary)
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
        try:
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
        except Exception:
            return False
