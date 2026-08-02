from __future__ import annotations

from typing import Any, Protocol

from app.modules.training.domain.submission import (
    TrainAndPredictCommand,
    TrainAndPredictSubmission,
    TrainingJobCommand,
)
from app.modules.training.domain.readiness import TrainingReadinessReport
from app.shared.api.schemas import Dataset, TrainingJob


class TrainingExecutionPort(Protocol):
    async def submit_job(self, command: TrainingJobCommand) -> TrainingJob: ...

    async def submit_train_and_predict(
        self,
        command: TrainAndPredictCommand,
    ) -> TrainAndPredictSubmission: ...

    async def cancel_job(self, job_id: str) -> bool: ...


class TrainingReadinessPort(Protocol):
    async def assess(
        self,
        *,
        dataset: Dataset,
        sample_ids: list[str] | None,
        sample_filter: dict[str, Any] | None,
        missing_image_policy: str | None,
    ) -> TrainingReadinessReport: ...


class TrainingDatasetUsagePort(Protocol):
    async def has_active_jobs(self, *, dataset_id: str, org_id: str) -> bool: ...


__all__ = [
    "TrainingDatasetUsagePort",
    "TrainingExecutionPort",
    "TrainingReadinessPort",
]
