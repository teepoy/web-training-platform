from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator


class CreateTrainingJobRequest(BaseModel):
    dataset_id: str
    trainer_id: str
    created_by: str = "demo-user"


class TrainAndPredictRequest(BaseModel):
    dataset_id: str
    trainer_id: str
    target: str = "image_classification"
    model_version: str | None = None
    sample_ids: list[str] | None = None
    sample_filter: dict[str, Any] | None = None
    prompt: str | None = None

    @model_validator(mode="after")
    def validate_sample_selection(self) -> TrainAndPredictRequest:
        if self.sample_ids is not None and self.sample_filter is not None:
            raise ValueError("sample_ids and sample_filter are mutually exclusive")
        return self


class TrainAndPredictResponse(BaseModel):
    train_job: dict
    workflow_run_id: str


class MarkLeftResponse(BaseModel):
    marked: bool
