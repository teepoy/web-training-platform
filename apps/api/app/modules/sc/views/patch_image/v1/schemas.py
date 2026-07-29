from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.core.registry import view


class ScImageRef(BaseModel):
    """Reference to one image embedded in the dataset's sparse shard.

    The ``url`` points at the generic per-sample image proxy
    (``GET /api/v1/datasets/{dataset_id}/samples/{sample_id}/images/{image_id}``),
    which streams the raw bytes from the v2 parquet shard. No external
    SC patch bucket dependency.
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
