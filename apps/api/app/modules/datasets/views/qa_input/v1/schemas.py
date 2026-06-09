from __future__ import annotations

from pydantic import BaseModel


class QAInputV1Row(BaseModel):
    sample_id: str
    image_uris: list[str]
    question: str
