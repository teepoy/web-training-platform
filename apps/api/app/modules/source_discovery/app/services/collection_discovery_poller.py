from __future__ import annotations

from datetime import datetime

from injector import inject

from app.modules.source_discovery.domain.models import (
    CollectionDiscoveryPoll,
    DiscoveryExecution,
)
from app.modules.source_discovery.domain.repository import SourceDiscoveryRepository
from app.modules.source_discovery.port.local import SourceDiscoveryManagementPort


class CollectionDiscoveryPoller:
    @inject
    def __init__(
        self,
        repository: SourceDiscoveryRepository,
        discovery: SourceDiscoveryManagementPort,
    ) -> None:
        self._repository = repository
        self._discovery = discovery

    async def poll_active_rules(
        self,
        *,
        as_of_utc: datetime,
        actor_id: str,
    ) -> CollectionDiscoveryPoll:
        executions: list[DiscoveryExecution] = []
        for rule in await self._repository.list_active_rules():
            executions.append(
                await self._discovery.run_live(
                    collection_id=rule.collection_id,
                    rule_id=rule.id,
                    org_id=rule.org_id,
                    actor_id=actor_id,
                    as_of_utc=as_of_utc,
                )
            )
        return CollectionDiscoveryPoll(
            as_of_utc=as_of_utc,
            executions=tuple(executions),
        )
