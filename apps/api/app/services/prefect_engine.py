"""PrefectWorkPoolEngine — TrainingExecutionEngine backed by Prefect deployments.

This module implements the :class:`~app.domain.interfaces.TrainingExecutionEngine`
Protocol using Prefect deployments. Flow runs are submitted via a pre-registered
deployment (``train-job-deployment``) which the embedded Prefect runner serves
inside the API process.

Design notes
------------
- Deployment must be registered by the embedded runner before jobs can be
  submitted.  The runner starts automatically in the API lifespan when
  ``execution.engine`` is set to ``prefect``.
- ``stream_events`` polls the Prefect API every 2 seconds, yielding state
  transitions and new log lines until the run reaches a terminal state.
- ``collect_artifacts`` reads artifact payload emitted by the flow run state.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.domain.models import ArtifactRef, TrainingEvent, TrainingJob
from app.domain.types import JobStatus
from app.services.prefect_client import PrefectClient

# ---------------------------------------------------------------------------
# State-mapping constants
# ---------------------------------------------------------------------------

_PREFECT_STATE_MAP: dict[str, JobStatus] = {
    "SCHEDULED": JobStatus.QUEUED,
    "PENDING": JobStatus.QUEUED,
    "RUNNING": JobStatus.RUNNING,
    "CANCELLING": JobStatus.RUNNING,
    "COMPLETED": JobStatus.COMPLETED,
    "FAILED": JobStatus.FAILED,
    "CRASHED": JobStatus.FAILED,
    "CANCELLED": JobStatus.CANCELLED,
}

_TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "CRASHED"}


class PrefectWorkPoolEngine:
    """Training engine that submits flow runs via a Prefect deployment.

    Parameters
    ----------
    prefect_client:
        Configured :class:`PrefectClient` instance.
    work_pool_name:
        Name of the Prefect work pool (kept for compatibility, not used).
    work_pool_type:
        Work pool type (kept for compatibility, not used).
    flow_name:
        Name of the Prefect flow (kept for compatibility, not used).
    deployment_name:
        Name of the deployment to submit runs to (default: ``train-job-deployment``).
    concurrency_limit:
        Maximum concurrent flow runs (kept for compatibility, not used).
    """

    def __init__(
        self,
        prefect_client: PrefectClient,
        work_pool_name: str,
        work_pool_type: str,
        flow_name: str,
        deployment_name: str = "train-job-deployment",
        concurrency_limit: int = 1,
        preset_registry: Any = None,
    ) -> None:
        self._client = prefect_client
        self._pool_name = work_pool_name
        self._pool_type = work_pool_type
        self._flow_name = flow_name
        self._default_deployment_name = deployment_name
        self._concurrency_limit = concurrency_limit
        self._preset_registry = preset_registry
        self._deployment_ids: dict[str, str] = {}
        self._queue_to_deployment: dict[str, str] = {
            "train-gpu": "train-job-torch-deployment",
            "optimize-llm-cpu": "train-job-dspy-deployment",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_deployment(self, deployment_name: str) -> str:
        """Resolve the deployment ID, caching it for subsequent calls.
        
        Raises HTTPException if deployment is not found.
        """
        if deployment_name not in self._deployment_ids:
            deployment_id = await self._client.resolve_deployment_id(deployment_name)
            if deployment_id is None:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail=f"Deployment '{deployment_name}' not found. "
                           "The embedded Prefect runner may still be starting up.",
                )
            self._deployment_ids[deployment_name] = deployment_id
        return self._deployment_ids[deployment_name]

    def _resolve_deployment_name(self, job: TrainingJob) -> str:
        if self._preset_registry is None:
            return self._default_deployment_name
        try:
            preset = self._preset_registry.get_preset(job.preset_id)
        except Exception:
            return self._default_deployment_name
        if preset is None:
            return self._default_deployment_name
        queue_name = getattr(getattr(preset, "runtime", None), "queue", None)
        if not queue_name:
            return self._default_deployment_name
        return self._queue_to_deployment.get(queue_name, self._default_deployment_name)

    # ------------------------------------------------------------------
    # TrainingExecutionEngine Protocol implementation
    # ------------------------------------------------------------------

    async def submit(self, job: TrainingJob) -> str:
        """Submit a training job as a Prefect flow run via deployment.

        Parameters
        ----------
        job:
            The :class:`~app.domain.models.TrainingJob` to execute.

        Returns
        -------
        str
            The Prefect flow-run UUID (used as ``external_job_id``).
        """
        deployment_name = self._resolve_deployment_name(job)
        deployment_id = await self._ensure_deployment(deployment_name)

        run = await self._client.create_flow_run_from_deployment(
            deployment_id=deployment_id,
            parameters={
                "job_id": job.id,
                "dataset_id": job.dataset_id,
                "preset_id": job.preset_id,
                "created_by": job.created_by,
            },
            idempotency_key=job.id,
        )
        return run["id"]

    async def status(self, external_job_id: str) -> JobStatus:
        """Return the current :class:`~app.domain.types.JobStatus` for a run.

        Parameters
        ----------
        external_job_id:
            Prefect flow-run UUID returned by :meth:`submit`.

        Returns
        -------
        JobStatus
            Mapped from the Prefect state type; defaults to ``QUEUED`` for
            unknown states.
        """
        run = await self._client.get_flow_run(external_job_id)
        state_type: str = run.get("state", {}).get("type", "PENDING")
        return _PREFECT_STATE_MAP.get(state_type, JobStatus.QUEUED)

    async def stream_events(self, external_job_id: str) -> AsyncIterator[TrainingEvent]:
        """Poll Prefect and yield events until the run reaches a terminal state.

        Yields state-change events and new log lines every 2 seconds.

        Parameters
        ----------
        external_job_id:
            Prefect flow-run UUID returned by :meth:`submit`.

        Yields
        ------
        TrainingEvent
        """
        # Extract job_id from the run's parameters for TrainingEvent attribution
        run = await self._client.get_flow_run(external_job_id)
        job_id: str = run.get("parameters", {}).get("job_id", external_job_id)

        last_log_count = 0
        prev_state = ""

        while True:
            await asyncio.sleep(2)

            run = await self._client.get_flow_run(external_job_id)
            state_type: str = run.get("state", {}).get("type", "")

            # Emit a state-change event when the Prefect state transitions
            if state_type and state_type != prev_state:
                yield TrainingEvent(
                    job_id=job_id,
                    ts=datetime.now(UTC),
                    message=f"prefect state: {state_type}",
                    payload={"prefect_state": state_type},
                )
                prev_state = state_type

            # Fetch logs and yield any that are new since last poll
            logs = await self._client.get_flow_run_logs(external_job_id)
            for log in logs[last_log_count:]:
                yield TrainingEvent(
                    job_id=job_id,
                    ts=datetime.now(UTC),
                    message=log.get("message", ""),
                    payload={"log_level": log.get("level", 0)},
                )
            last_log_count = len(logs)

            # Stop polling once the run has finished
            if state_type in _TERMINAL_STATES:
                break

        # Determine final human-readable status
        if prev_state == "COMPLETED":
            final_status = "completed"
        elif prev_state in {"FAILED", "CRASHED"}:
            final_status = "failed"
        elif prev_state == "CANCELLED":
            final_status = "cancelled"
        else:
            final_status = "failed"

        yield TrainingEvent(
            job_id=job_id,
            ts=datetime.now(UTC),
            message=f"training {final_status}",
            payload={"status": final_status},
        )

    async def cancel(self, external_job_id: str) -> bool:
        """Request cancellation of a running flow run.

        Parameters
        ----------
        external_job_id:
            Prefect flow-run UUID.

        Returns
        -------
        bool
            ``True`` if the cancellation request was accepted, ``False`` on error.
        """
        try:
            await self._client.set_flow_run_state(external_job_id, "CANCELLING")
            return True
        except Exception:
            return False

    async def collect_artifacts(self, external_job_id: str) -> list[ArtifactRef]:
        """Return artifact references for a completed flow run.

        Attempts to extract result information from the run state.
        Returns an empty list when artifacts are unavailable.

        Parameters
        ----------
        external_job_id:
            Prefect flow-run UUID.

        Returns
        -------
        list[ArtifactRef]
        """
        try:
            run = await self._client.get_flow_run(external_job_id)
            state_data = run.get("state", {}).get("data", {})
            if isinstance(state_data, dict) and state_data.get("artifacts"):
                return [
                    ArtifactRef(
                        uri=a["uri"],
                        kind=a.get("kind", "artifact"),
                        metadata=a.get("metadata", {}) if isinstance(a.get("metadata", {}), dict) else {},
                    )
                    for a in state_data["artifacts"]
                    if isinstance(a, dict) and a.get("uri")
                ]
        except Exception:
            return []
        return []
