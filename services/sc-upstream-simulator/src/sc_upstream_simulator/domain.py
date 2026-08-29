from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


@dataclass(frozen=True)
class InspectionKey:
    wafer_key: int
    inspection_time: datetime

    def __post_init__(self) -> None:
        _require_aware(self.inspection_time, "inspection_time")


@dataclass(frozen=True)
class DefectDraft:
    defect_id: int
    test_id: int
    class_number: int
    rough_bin: int
    wafer_x: int
    wafer_y: int
    index_x: int
    index_y: int
    adder: int
    cluster: int
    images: int
    size_x: int
    size_y: int
    size_d: int
    area: int
    final_bin: int
    manual_bin: int
    kill_ratio: float


@dataclass(frozen=True)
class ReviewImageDraft:
    defect_id: int
    image_id: int
    image_type: str
    image_filespec: str


@dataclass(frozen=True)
class PatchArchiveDraft:
    archive_id: int
    s3_bucket: str
    s3_key: str


@dataclass(frozen=True)
class InspectionDraft:
    key: InspectionKey
    lot_id: str
    wafer_id: str
    layer_id: str
    device: str
    inspect_equip_id: str
    recipe_key: int
    recipe_id: str
    origin_index_x: int
    origin_index_y: int
    center_x: int
    center_y: int
    origin_x: int
    origin_y: int
    die_size_x: int
    die_size_y: int
    defects: tuple[DefectDraft, ...]
    review_images: tuple[ReviewImageDraft, ...]
    patch_archives: tuple[PatchArchiveDraft, ...]


@dataclass(frozen=True)
class Publication:
    key: InspectionKey
    published_at: datetime
    last_updated_at: datetime
    change_token: int
