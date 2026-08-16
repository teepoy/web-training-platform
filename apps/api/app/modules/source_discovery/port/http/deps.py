from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.source_discovery.port.local import SourceDiscoveryManagementPort
from app.shared.injection import resolve


def get_source_discovery_service(request: Request) -> SourceDiscoveryManagementPort:
    return resolve(request, SourceDiscoveryManagementPort)


SourceDiscoveryServiceDep = Annotated[
    SourceDiscoveryManagementPort, Depends(get_source_discovery_service)
]
