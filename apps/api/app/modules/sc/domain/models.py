"""SC domain model definitions.

Per CORE_DESIGNS.md §2: module domain models live in the owning module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

_SC_UPSTREAM_TZ = ZoneInfo("Asia/Shanghai")


def _coerce_naive_to_upstream_tz(dt: datetime) -> datetime:
    """If dt has no tzinfo, assume Asia/Shanghai. Does NOT convert to UTC — preserves wall clock values."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_SC_UPSTREAM_TZ)
    return dt


class ScImageError(Exception):
    pass


class ScImageNotFoundError(ScImageError):
    pass


class ScImageUpstreamError(ScImageError):
    pass


class ScImageCacheError(ScImageError):
    pass


def parse_inspection_time(raw: object) -> datetime | None:
    """Parse an inspection time value into a UTC datetime.

    Naive datetime values (no timezone) are assumed to be in Asia/Shanghai
    (the source upstream timezone) and then converted to UTC.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return _coerce_naive_to_upstream_tz(raw)
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw)
            return _coerce_naive_to_upstream_tz(dt)
        except ValueError:
            return None
    return None


class PatchImage(BaseModel):
    image_name: str


class ReviewImage(BaseModel):
    image_url: str
    image_name: str
    image_id: int
    image_type: str


@dataclass(frozen=True, slots=True)
class WaferPointSummary:
    """Lightweight wafer point summary for efficient listing (100K+ instances).

    Domain-internal type — not a transport schema. Uses frozen+slots dataclass
    for minimal memory overhead.
    """

    defect_id: str
    wafer_x: int
    wafer_y: int
    die_x: int
    die_y: int
    class_number: int | None
    rough_bin: int


class ShardImageRef(BaseModel):
    image_id: str
    image_type: str = ""
    role: str = ""
    content_type: str = ""
    filename: str = ""
    bytes: Any = Field(default=None, exclude=True)


class PatchSample(BaseModel):
    """Base SC PatchSample domain model.

    The ``@dataset``-decorated subclass with registration metadata lives in
    ``app.modules.sc.models.PatchSample``.
    """

    sample_id: str
    inspection_time: datetime | None = None
    wafer_key: int = 0
    defect_id: str = ""
    lot_id: str = ""
    wafer_x: int = 0
    wafer_y: int = 0
    die_x: int = 0
    die_y: int = 0
    rough_bin: int = 0
    class_number: int | None = None
    test_id: int | None = None
    review_images: list[ReviewImage] = Field(default_factory=list)
    shard_images: list[ShardImageRef] = Field(default_factory=list)
    label: str = ""


class InspectionSummary(BaseModel):
    inspection_time: datetime
    wafer_key: int
    center_x: int
    center_y: int
    origin_x: int
    origin_y: int
    die_size_x: int
    die_size_y: int
    test_id: str | None = None
    layer_id: str | None = None
    eqp_id: str | None = None
    recipe_id: str | None = None
    device: str
    defects: int = 0
    images: int = 0
    samples: list[PatchSample] = []


class ScInspectionRecord(BaseModel):
    """Lightweight inspection summary row returned by listing queries.

    Contains inspection metadata without sample data for efficient listing.
    """

    inspection_time: datetime
    wafer_key: int
    lot_id: str = ""
    wafer_id: str = ""
    center_x: int = 0
    center_y: int = 0
    origin_x: int = 0
    origin_y: int = 0
    die_size_x: int = 0
    die_size_y: int = 0
    layer_id: str | None = None
    eqp_id: str | None = None
    recipe_id: str = ""
    defects: int = 0
    images: int = 0
    device: str
    origin_index_x: int = 0
    origin_index_y: int = 0
    latest_update: int = 0
