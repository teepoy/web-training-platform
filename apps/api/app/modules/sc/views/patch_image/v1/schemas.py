from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.core.registry import view


class ScImageRef(BaseModel):
    """Reference to one SC image exposed through a dataset-owned proxy.

    Existing source schema v2 rows may resolve embedded bytes or persisted
    locators. Source schema v3 rows derive patch references from scalar sample
    identity when this view is requested; no image structs are stored per row.
    """

    role: str
    image_id: str
    image_type: str = ""
    content_type: str = ""
    url: str
    bytes: Any = Field(default=None, exclude=True)


@view(id="patch_image_v1")
class ScPatchImageV1Row(BaseModel):
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
    images: list[ScImageRef] = Field(default_factory=list)
    review_images: list[dict] = Field(default_factory=list)
    label: int | str = ""
    predicted_label: int | str = ""
    confidence: float | None = None
