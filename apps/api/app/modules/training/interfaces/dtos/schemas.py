from __future__ import annotations

from pydantic import BaseModel


class CreateTrainingJobRequest(BaseModel):
    dataset_id: str
    preset_id: str
    created_by: str = "demo-user"


class MarkLeftResponse(BaseModel):
    marked: bool
