from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.training.domain.submission import (
    TrainAndPredictCommand,
    TrainingJobCommand,
)
from app.shared.api.schemas import TrainingJob


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateTrainingJobRequest(_StrictRequest):
    dataset_id: str = Field(min_length=1)
    trainer_id: str = Field(min_length=1)

    def to_command(self, *, org_id: str, created_by: str) -> TrainingJobCommand:
        return TrainingJobCommand(
            dataset_id=self.dataset_id,
            trainer_id=self.trainer_id,
            org_id=org_id,
            created_by=created_by,
        )


class TrainAndPredictRequest(_StrictRequest):
    dataset_id: str = Field(min_length=1)
    trainer_id: str = Field(min_length=1)
    target: str = Field(default="image_classification", min_length=1)
    model_version: str | None = None
    sample_ids: list[str] | None = Field(default=None, min_length=1)
    sample_filter: dict[str, Any] | None = None
    prompt: str | None = None
    predictor_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_sample_selection(self) -> TrainAndPredictRequest:
        if self.sample_ids is not None and self.sample_filter is not None:
            raise ValueError("sample_ids and sample_filter are mutually exclusive")
        if self.sample_filter is not None and not self.sample_filter:
            raise ValueError("sample_filter must not be empty")
        return self

    def to_command(self, *, org_id: str, created_by: str) -> TrainAndPredictCommand:
        return TrainAndPredictCommand(
            dataset_id=self.dataset_id,
            trainer_id=self.trainer_id,
            org_id=org_id,
            created_by=created_by,
            target=self.target,
            model_version=self.model_version,
            sample_ids=tuple(self.sample_ids) if self.sample_ids is not None else None,
            sample_filter=self.sample_filter,
            prompt=self.prompt,
            predictor_id=self.predictor_id,
        )


class TrainAndPredictResponse(BaseModel):
    train_job: TrainingJob
    workflow_run_id: str


class MarkLeftResponse(BaseModel):
    marked: bool
