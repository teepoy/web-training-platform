from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from prefect.client.orchestration import get_client
from prefect.client.schemas.objects import StateType

logger = logging.getLogger(__name__)

_TERMINAL_STATES: set[StateType] = {
    StateType.COMPLETED,
    StateType.FAILED,
    StateType.CRASHED,
    StateType.CANCELLED,
    StateType.CANCELLING,
}


class PrefectFlowRunError(Exception):
    """Flow run did not complete successfully."""


class PrefectFlowRunTimeout(PrefectFlowRunError):
    """Flow run did not complete within the allotted timeout."""


async def submit_flow_run_and_wait(
    deployment_name: str,
    parameters: dict[str, Any],
    *,
    timeout_seconds: float = 300.0,
    poll_interval: float = 0.5,
) -> dict[str, Any]:
    """Submit a flow run from a deployment and poll until it reaches a terminal state.

    Parameters
    ----------
    deployment_name:
        Prefect deployment name (e.g. ``"training/train-job"``).
    parameters:
        Parameter overrides to pass to the flow run.
    timeout_seconds:
        Maximum seconds to wait for the flow run to reach a terminal state.
        Defaults to 300.
    poll_interval:
        Seconds between state polls. Defaults to 0.5.

    Returns
    -------
    dict[str, Any]
        The flow-run result returned by Prefect on successful completion.

    Raises
    ------
    PrefectFlowRunError
        If the flow run fails, crashes, or is cancelled.
    PrefectFlowRunTimeout
        If the flow run does not reach a terminal state within *timeout_seconds*.
    """
    async with get_client() as client:
        deployment = await client.read_deployment_by_name(deployment_name)
        deployment_id: UUID = deployment.id

        flow_run = await client.create_flow_run_from_deployment(
            deployment_id,
            parameters=parameters,
        )
        flow_run_id = flow_run.id
        logger.info(
            "Submitted flow run %s for deployment %r", flow_run_id, deployment_name
        )

        elapsed = 0.0
        while elapsed < timeout_seconds:
            flow_run = await client.read_flow_run(flow_run_id)
            state = flow_run.state
            state_type: StateType | None = state.type if state is not None else None

            if state_type is None:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue

            if state_type not in _TERMINAL_STATES:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue

            if state_type == StateType.COMPLETED:
                logger.info("Flow run %s completed in %.1fs", flow_run_id, elapsed)
                assert state is not None
                result = state.result()
                if isinstance(result, dict):
                    return result
                return {}

            if state_type in (StateType.FAILED, StateType.CRASHED):
                msg = (
                    f"Flow run {flow_run_id} {state_type.value}: "
                    f"{state.message if state else 'unknown error'}"
                )
                logger.error(msg)
                raise PrefectFlowRunError(msg)

            if state_type in (StateType.CANCELLED, StateType.CANCELLING):
                logger.warning("Flow run %s was cancelled", flow_run_id)
                raise PrefectFlowRunError(f"Flow run {flow_run_id} was cancelled")

        raise PrefectFlowRunTimeout(
            f"Flow run {flow_run_id} did not complete within {timeout_seconds}s"
        )
