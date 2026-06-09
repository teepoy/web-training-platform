from __future__ import annotations

from pydantic import BaseModel


class LabeledImageV1Row(BaseModel):
    sample_id: str
    image_uris: list[str]
    label: str
