from __future__ import annotations

from typing import Any, Protocol

from app.shared.api.schemas import TrainingJob


class TaskTrackerPort(Protocol):
    async def list_jobs(self, org_id: str | None = None) -> list[TrainingJob]: ...


class TaskTrackerServicePort(Protocol):
    async def list_tasks(self, *args: Any, **kwargs: Any) -> Any: ...

    async def get_task(self, *args: Any, **kwargs: Any) -> Any: ...

    async def cancel_task(self, task_id: str, org_id: str) -> bool: ...
