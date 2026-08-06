"""PrefectWorkPoolEngine — TrainingExecutionEngine backed by Prefect deployments.

This module implements the :class:`~app.shared.infrastructure.storage.base.TrainingExecutionEngine`
Protocol using Prefect deployments. Flow runs are submitted through the
module-owned runtime capability descriptor plus optional environment overrides.

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

from app.shared.api.schemas import ArtifactRef, TrainingEvent, TrainingJob
from app.shared.api.schemas import JobStatus
from app.modules.runtime.app.services.deployment_seed import TRAIN_RUNTIME_DEPLOYMENT
from app.shared.domain.protocols import PrefectClient

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
    """

    def __init__(
        self,
        prefect_client: PrefectClient,
    ) -> None:
        self._client = prefect_client
        self._deployment_ids: dict[str, str] = {}

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

    # ------------------------------------------------------------------
    # TrainingExecutionEngine Protocol implementation
    # ------------------------------------------------------------------

    async def submit(self, job: TrainingJob) -> str:
        """Submit a training job as a Prefect flow run via deployment.

        Parameters
        ----------
        job:
            The :class:`~app.shared.api.schemas.TrainingJob` to execute.

        Returns
        -------
        str
            The Prefect flow-run UUID (used as ``external_job_id``).
        """
        if job.dataset_id is None and (
            job.collection_id is None or job.collection_revision_id is None
        ):
            raise ValueError(f"Source data for training job '{job.id}' is unavailable")
        deployment_name = TRAIN_RUNTIME_DEPLOYMENT.deployment_name
        deployment_id = await self._ensure_deployment(deployment_name)

        run = await self._client.create_flow_run_from_deployment(
            deployment_id=deployment_id,
            parameters={
                "job_id": job.id,
                "dataset_id": job.dataset_id,
                "collection_id": job.collection_id,
                "collection_revision_id": job.collection_revision_id,
                "org_id": job.org_id or "",
                "trainer_id": job.trainer_id,
                "created_by": job.created_by,
            },
            idempotency_key=job.id,
        )
        return run["id"]

    async def status(self, external_job_id: str) -> JobStatus:
        """Return the current :class:`~app.shared.api.schemas.JobStatus` for a run.

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

        # ── Emit epoch + metric events from flow run result ──────────
        if prev_state == "COMPLETED":
            run = await self._client.get_flow_run(external_job_id)
            state_data = run.get("state", {}).get("data", {})
            metrics = (
                state_data.get("metrics", {}) if isinstance(state_data, dict) else {}
            )
            if isinstance(metrics, dict) and metrics:
                metric_payload: dict[str, object] = dict(metrics)
                yield TrainingEvent(
                    job_id=job_id,
                    ts=datetime.now(UTC),
                    level="metric",
                    message="training metrics",
                    payload=metric_payload,
                )
                epochs = metrics.get("epochs", 0)
                epoch_losses = (
                    metrics.get("epoch_losses", [])
                    if isinstance(metrics.get("epoch_losses"), list)
                    else []
                )
                for ep in range(1, int(epochs) + 1):
                    ep_payload: dict[str, object] = {"epoch": ep}
                    if ep - 1 < len(epoch_losses):
                        ep_payload["val/loss"] = float(epoch_losses[ep - 1])
                    yield TrainingEvent(
                        job_id=job_id,
                        ts=datetime.now(UTC),
                        level="epoch",
                        message=f"epoch {ep} completed",
                        payload=ep_payload,
                    )

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
                        metadata=a.get("metadata", {})
                        if isinstance(a.get("metadata", {}), dict)
                        else {},
                    )
                    for a in state_data["artifacts"]
                    if isinstance(a, dict) and a.get("uri")
                ]
        except Exception:
            return []
        return []
