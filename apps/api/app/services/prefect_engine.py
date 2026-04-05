"""PrefectWorkPoolEngine — TrainingExecutionEngine backed by Prefect work pools.

This module implements the :class:`~app.domain.interfaces.TrainingExecutionEngine`
Protocol using direct Prefect flow run submission (no deployments).  All Prefect
communication is delegated to :class:`~app.services.prefect_client.PrefectClient`
via plain httpx REST calls — no ``prefect`` Python SDK is imported here.

Design notes
------------
- Work pool is lazily ensured on first ``submit()`` call.
- Flow ID is resolved (and auto-created) per submission via ``resolve_flow_id``.
- ``stream_events`` polls the Prefect API every 2 seconds, yielding state
  transitions and new log lines until the run reaches a terminal state.
- ``collect_artifacts`` returns placeholder S3 URIs matching the
  ``LocalProcessEngine`` convention; extend this as needed once a real
  artifact store is wired.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

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
    """Training engine that submits flow runs to a Prefect work pool.

    Parameters
    ----------
    prefect_client:
        Configured :class:`PrefectClient` instance.
    work_pool_name:
        Name of the Prefect work pool to create/use.
    work_pool_type:
        Work pool type (e.g. ``"process"`` or ``"kubernetes"``).
    flow_name:
        Name of the Prefect flow to register and run.
    concurrency_limit:
        Maximum concurrent flow runs on the work pool (default 1).
    """

    def __init__(
        self,
        prefect_client: PrefectClient,
        work_pool_name: str,
        work_pool_type: str,
        flow_name: str,
        concurrency_limit: int = 1,
    ) -> None:
        self._client = prefect_client
        self._pool_name = work_pool_name
        self._pool_type = work_pool_type
        self._flow_name = flow_name
        self._concurrency_limit = concurrency_limit
        self._pool_ensured: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_pool(self) -> None:
        """Create or verify the work pool on first use."""
        if not self._pool_ensured:
            await self._client.ensure_work_pool(
                self._pool_name,
                self._pool_type,
                self._concurrency_limit,
            )
            self._pool_ensured = True

    # ------------------------------------------------------------------
    # TrainingExecutionEngine Protocol implementation
    # ------------------------------------------------------------------

    async def submit(self, job: TrainingJob) -> str:
        """Submit a training job as a Prefect flow run.

        Parameters
        ----------
        job:
            The :class:`~app.domain.models.TrainingJob` to execute.

        Returns
        -------
        str
            The Prefect flow-run UUID (used as ``external_job_id``).
        """
        await self._ensure_pool()

        flow_id = await self._client.resolve_flow_id(self._flow_name)

        run = await self._client.create_flow_run(
            flow_id=flow_id,
            work_pool_name=self._pool_name,
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

        Attempts to extract result information from the run state; falls back
        to conventional placeholder S3 URIs when no artifact data is available.

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
            # Attempt to find artifact URIs embedded in the run state data
            state_data = run.get("state", {}).get("data", {})
            if isinstance(state_data, dict) and state_data.get("artifacts"):
                return [
                    ArtifactRef(uri=a["uri"], kind=a.get("kind", "artifact"))
                    for a in state_data["artifacts"]
                    if isinstance(a, dict) and a.get("uri")
                ]
        except Exception:
            pass

        # Fallback: conventional placeholder artifacts
        return [
            ArtifactRef(
                uri=f"s3://artifacts/prefect/{external_job_id}/model",
                kind="model",
            ),
            ArtifactRef(
                uri=f"s3://artifacts/prefect/{external_job_id}/metrics.json",
                kind="metrics",
            ),
        ]
