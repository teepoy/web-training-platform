from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from app.modules.source_discovery.adapter.flows.collection_discovery import (
    execute_collection_discovery_poll,
)
from app.modules.source_discovery.domain.models import (
    CollectionDiscoveryPoll,
    DiscoveryExecution,
    DiscoveryRun,
)
from app.modules.source_discovery.port.local import CollectionDiscoveryPollingPort
from app.shared.context import AppContext


def _execution(status: str) -> DiscoveryExecution:
    now = datetime(2026, 8, 29, tzinfo=UTC)
    return DiscoveryExecution(
        run=DiscoveryRun(
            id=f"run-{status}",
            org_id="org",
            collection_id="collection",
            rule_id="rule",
            rule_version_id="rule-version",
            kind="live",
            status=status,
            as_of_utc=now,
            range_start_utc=now,
            range_end_utc=now,
            timezone_name=None,
            parent_run_id=None,
            collection_revision_id=None,
            stats={},
            error_detail=None,
            created_by="system:collection-discovery",
            created_at=now,
            completed_at=now,
        )
    )


class _PollingPort:
    def __init__(self, status: str) -> None:
        self._status = status

    async def poll_active_rules(
        self, *, as_of_utc: datetime, actor_id: str
    ) -> CollectionDiscoveryPoll:
        assert actor_id == "system:collection-discovery"
        return CollectionDiscoveryPoll(
            as_of_utc=as_of_utc,
            executions=(_execution(self._status),),
        )


class _Injector:
    def __init__(self, polling: CollectionDiscoveryPollingPort) -> None:
        self._polling = polling

    def get(self, interface: object) -> CollectionDiscoveryPollingPort:
        assert interface is CollectionDiscoveryPollingPort
        return self._polling


@pytest.mark.asyncio
async def test_poll_flow_reports_status_counts() -> None:
    observed_at = datetime(2026, 8, 29, 12, tzinfo=UTC)
    context = cast(
        AppContext,
        cast(object, type("Context", (), {"injector": _Injector(_PollingPort("skipped"))})()),
    )

    result = await execute_collection_discovery_poll(
        as_of_utc=observed_at,
        app_context=context,
    )

    assert result["rules"] == 1
    assert result["skipped"] == 1
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_poll_flow_fails_when_an_upstream_rule_fails() -> None:
    context = cast(
        AppContext,
        cast(object, type("Context", (), {"injector": _Injector(_PollingPort("failed"))})()),
    )

    with pytest.raises(RuntimeError, match="1 Collection discovery rule"):
        await execute_collection_discovery_poll(
            as_of_utc=datetime(2026, 8, 29, 12, tzinfo=UTC),
            app_context=context,
        )
