from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from app.core.registry import view


@view(id="image_input_v1")
class ImageInputV1Row(BaseModel):
    view_id: ClassVar[str]
    view_name: ClassVar[str]
    is_annotation_view: ClassVar[bool]

    sample_id: str
    image_uris: list[str]
