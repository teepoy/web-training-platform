from __future__ import annotations

from pydantic import BaseModel, Field


class BoxV1Row(BaseModel):
    label: str
    x: float
    y: float
    width: float
    height: float


class BoxDetectionV1Row(BaseModel):
    sample_id: str
    image_uris: list[str]
    boxes: list[BoxV1Row] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None
