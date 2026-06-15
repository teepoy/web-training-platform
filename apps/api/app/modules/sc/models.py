from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from app.core.registry import dataset
from app.modules.sc.domain.models import (
    InspectionSummary as _InspectionSummary,
    PatchImage as _PatchImage,
    PatchSample as _PatchSample,
    ReviewImage as _ReviewImage,
    ShardImageRef as _ShardImageRef,
)


PatchImage = _PatchImage
ReviewImage = _ReviewImage
ShardImageRef = _ShardImageRef
InspectionSummary = _InspectionSummary


@dataset
class PatchSample(_PatchSample):
    ID: ClassVar[str] = "image_sc"
    VIEW_TYPES: ClassVar[set[str]] = {
        "image_input_v1",
        "patch_image_v1",
        "review_image_v1",
    }
    TASK_TYPE: ClassVar[str] = "sc"


class ScDataset(BaseModel):
    dataset_id: str
    name: str
    task_type: str = "patch"
    storage_mode: str = "file_shard_sparse"
    ls_project_id: str = ""
    samples: list[PatchSample] = []
    metadata: dict = {}
