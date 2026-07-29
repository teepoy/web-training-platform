from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from app.core.registry import view


@view(id="review_image_v1")
class ScReviewImageV1Row(BaseModel):
    view_id: ClassVar[str]
    view_name: ClassVar[str]
    is_annotation_view: ClassVar[bool]

    sample_id: str
    inspection_time: str
    wafer_key: int
    defect_id: str
    wafer_x: int
    wafer_y: int
    die_x: int = 0
    die_y: int = 0
    rough_bin: int
    class_number: int | None = None
    review_images: list[dict]
