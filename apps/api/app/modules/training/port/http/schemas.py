from __future__ import annotations

from pydantic import BaseModel


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
    prompt: str | None = None


class TrainAndPredictResponse(BaseModel):
    train_job: dict
    workflow_run_id: str


class MarkLeftResponse(BaseModel):
    marked: bool
