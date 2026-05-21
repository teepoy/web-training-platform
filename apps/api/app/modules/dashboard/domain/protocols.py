from __future__ import annotations

from typing import Protocol

from app.shared.api.schemas import TrainingJob


class JobRepository(Protocol):
    async def list_jobs(self, org_id: str | None = None) -> list[TrainingJob]: ...
