from __future__ import annotations

from datetime import UTC, datetime

from prefect import flow, get_run_logger

from app.composition import build_flow_app_context, close_flow_app_context
from app.core.config import load_config
from app.modules.source_discovery.port.local import CollectionDiscoveryPollingPort
from app.shared.context import AppContext

SYSTEM_ACTOR = "system:collection-discovery"


async def execute_collection_discovery_poll(
    *,
    as_of_utc: datetime | None = None,
    app_context: AppContext | None = None,
) -> dict[str, object]:
    owns_context = app_context is None
    if app_context is None:
        app_context = build_flow_app_context(load_config(skip_runtime_validation=True))
    try:
        if app_context.injector is None:
            raise RuntimeError("AppContext injector was not initialized")
        observed_at = as_of_utc or datetime.now(UTC)
        poll = await app_context.injector.get(
            CollectionDiscoveryPollingPort
        ).poll_active_rules(
            as_of_utc=observed_at,
            actor_id=SYSTEM_ACTOR,
        )
        statuses = [execution.run.status for execution in poll.executions]
        failed = statuses.count("failed")
        result: dict[str, object] = {
            "as_of_utc": poll.as_of_utc.isoformat(),
            "rules": len(statuses),
            "completed": statuses.count("completed"),
            "partial": statuses.count("partial"),
            "needs_attention": statuses.count("needs_attention"),
            "skipped": statuses.count("skipped"),
            "failed": failed,
            "run_ids": [execution.run.id for execution in poll.executions],
        }
        if failed:
            raise RuntimeError(f"{failed} Collection discovery rule(s) failed")
        return result
    finally:
        if owns_context:
            await close_flow_app_context(app_context)


@flow(name="collection-discovery-poll")
async def collection_discovery_poll() -> dict[str, object]:
    result = await execute_collection_discovery_poll()
    get_run_logger().info("Collection discovery poll: %s", result)
    return result


__all__ = ["collection_discovery_poll", "execute_collection_discovery_poll"]
