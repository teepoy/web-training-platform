from __future__ import annotations

from typing import Any, Protocol

from app.shared.api.schemas import DashboardResponse


class DashboardQueryPort(Protocol):
    async def get_dashboard_data(self, org_id: str) -> DashboardResponse: ...


class ServiceHealthPort(Protocol):
    async def check_all(self) -> list[Any]: ...


__all__ = ["DashboardQueryPort", "ServiceHealthPort"]
