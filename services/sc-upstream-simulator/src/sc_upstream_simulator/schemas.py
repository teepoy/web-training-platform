from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .domain import (
    DefectDraft,
    InspectionDraft,
    InspectionKey,
    InspectionRecord,
    PatchArchiveDraft,
    Publication,
    ReviewImageDraft,
)


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InspectionKeyBody(StrictModel):
    wafer_key: int
    inspection_time: datetime

    @field_validator("inspection_time")
    @classmethod
    def inspection_time_is_aware(cls, value: datetime) -> datetime:
        return _aware(value, "inspection_time")

    def to_key(self) -> InspectionKey:
        return InspectionKey(
            wafer_key=self.wafer_key, inspection_time=self.inspection_time
        )


class DefectBody(StrictModel):
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

    def to_domain(self) -> DefectDraft:
        return DefectDraft(**self.model_dump())


class ReviewImageBody(StrictModel):
    defect_id: int
    image_id: int
    image_type: str
    image_filespec: str

    def to_domain(self) -> ReviewImageDraft:
        return ReviewImageDraft(**self.model_dump())


class PatchArchiveBody(StrictModel):
    archive_id: int
    s3_bucket: str
    s3_key: str

    def to_domain(self) -> PatchArchiveDraft:
        return PatchArchiveDraft(**self.model_dump())


class CreateInspectionRequest(InspectionKeyBody):
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
    defects: tuple[DefectBody, ...]
    review_images: tuple[ReviewImageBody, ...]
    patch_archives: tuple[PatchArchiveBody, ...]

    def to_domain(self) -> InspectionDraft:
        return InspectionDraft(
            key=self.to_domain_key(),
            lot_id=self.lot_id,
            wafer_id=self.wafer_id,
            layer_id=self.layer_id,
            device=self.device,
            inspect_equip_id=self.inspect_equip_id,
            recipe_key=self.recipe_key,
            recipe_id=self.recipe_id,
            origin_index_x=self.origin_index_x,
            origin_index_y=self.origin_index_y,
            center_x=self.center_x,
            center_y=self.center_y,
            origin_x=self.origin_x,
            origin_y=self.origin_y,
            die_size_x=self.die_size_x,
            die_size_y=self.die_size_y,
            defects=tuple(item.to_domain() for item in self.defects),
            review_images=tuple(item.to_domain() for item in self.review_images),
            patch_archives=tuple(item.to_domain() for item in self.patch_archives),
        )

    def to_domain_key(self) -> InspectionKey:
        return self.to_key()


class AppendRecordsRequest(InspectionKeyBody):
    defects: tuple[DefectBody, ...]
    review_images: tuple[ReviewImageBody, ...]
    patch_archives: tuple[PatchArchiveBody, ...]

    @model_validator(mode="after")
    def has_records(self) -> AppendRecordsRequest:
        if not self.defects and not self.review_images and not self.patch_archives:
            raise ValueError("at least one child record is required")
        return self


class PublishInspectionRequest(InspectionKeyBody):
    published_at: datetime

    @field_validator("published_at")
    @classmethod
    def published_at_is_aware(cls, value: datetime) -> datetime:
        return _aware(value, "published_at")


class UpdateInspectionRequest(InspectionKeyBody):
    changed_at: datetime
    lot_id: str | None = None
    wafer_id: str | None = None
    layer_id: str | None = None
    device: str | None = None
    inspect_equip_id: str | None = None
    recipe_key: int | None = None
    recipe_id: str | None = None
    origin_index_x: int | None = None
    origin_index_y: int | None = None
    center_x: int | None = None
    center_y: int | None = None
    origin_x: int | None = None
    origin_y: int | None = None
    die_size_x: int | None = None
    die_size_y: int | None = None

    @field_validator("changed_at")
    @classmethod
    def changed_at_is_aware(cls, value: datetime) -> datetime:
        return _aware(value, "changed_at")

    @model_validator(mode="after")
    def has_changes(self) -> UpdateInspectionRequest:
        if not self.changes():
            raise ValueError("at least one mutable field is required")
        return self

    def changes(self) -> dict[str, str | int]:
        values = self.model_dump(
            exclude_unset=True,
            exclude={"wafer_key", "inspection_time", "changed_at"},
        )
        return {name: value for name, value in values.items() if value is not None}


class InspectionResponse(StrictModel):
    wafer_key: int
    inspection_time: datetime
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
    state: Literal["draft", "published"]
    published_at: datetime | None
    last_updated_at: datetime | None
    change_token: int | None

    @classmethod
    def from_domain(cls, record: InspectionRecord) -> InspectionResponse:
        return cls(
            wafer_key=record.key.wafer_key,
            inspection_time=record.key.inspection_time,
            lot_id=record.lot_id,
            wafer_id=record.wafer_id,
            layer_id=record.layer_id,
            device=record.device,
            inspect_equip_id=record.inspect_equip_id,
            recipe_key=record.recipe_key,
            recipe_id=record.recipe_id,
            origin_index_x=record.origin_index_x,
            origin_index_y=record.origin_index_y,
            center_x=record.center_x,
            center_y=record.center_y,
            origin_x=record.origin_x,
            origin_y=record.origin_y,
            die_size_x=record.die_size_x,
            die_size_y=record.die_size_y,
            state=record.state,
            published_at=record.published_at,
            last_updated_at=record.last_updated_at,
            change_token=record.change_token,
        )


class PublicationResponse(StrictModel):
    wafer_key: int
    inspection_time: datetime
    published_at: datetime
    last_updated_at: datetime
    change_token: int

    @classmethod
    def from_domain(cls, publication: Publication) -> PublicationResponse:
        return cls(
            wafer_key=publication.key.wafer_key,
            inspection_time=publication.key.inspection_time,
            published_at=publication.published_at,
            last_updated_at=publication.last_updated_at,
            change_token=publication.change_token,
        )
