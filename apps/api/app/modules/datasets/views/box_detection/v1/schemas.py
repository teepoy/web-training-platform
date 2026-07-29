from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from app.core.registry import view


class BoxV1Row(BaseModel):
    label: str
    x: float
    y: float
    width: float
    height: float


@view(id="box_detection_v1")
class BoxDetectionV1Row(BaseModel):
    view_id: ClassVar[str]
    view_name: ClassVar[str]
    is_annotation_view: ClassVar[bool]

    sample_id: str
    image_uris: list[str]
    boxes: list[BoxV1Row] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None
