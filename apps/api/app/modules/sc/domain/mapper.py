from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote
from uuid import uuid4

from app.core.mapper_registry import mapper
from app.shared.api.schemas import Sample

from app.modules.sc.domain.models import (
    PatchSample,
    ReviewImage,
    ShardImageRef,
    parse_inspection_time,
)
from app.modules.sc.models import PatchSample as DecoratedPatchSample
from app.modules.sc.views.patch_image.v1.schemas import ScImageRef, ScPatchImageV1Row
from app.modules.sc.views.review_image.v1.schemas import ScReviewImageV1Row

if TYPE_CHECKING:
    pass


# ── from_sample ────────────────────────────────────────────────────────


@mapper.register([Sample], [DecoratedPatchSample, DecoratedPatchSample.ID])
def from_sample_to_patch_sample(sample: Sample | dict) -> DecoratedPatchSample:
    if isinstance(sample, dict):
        raw = sample
    else:
        raw = {
            "id": getattr(sample, "id", ""),
            "image_uris": getattr(sample, "image_uris", []),
            "metadata": getattr(
                sample, "metadata", getattr(sample, "metadata_json", {})
            ),
        }

    meta: dict = raw.get("metadata", {})
    if not isinstance(meta, dict):
        meta = {}

    review_images: list[ReviewImage] = []
    ri = meta.get("review_images")
    if isinstance(ri, list):
        for r in ri:
            if isinstance(r, dict):
                review_images.append(
                    ReviewImage(
                        image_url=str(r.get("image_url", "")),
                        image_name=str(r.get("image_name", "")),
                        image_id=int(r.get("image_id", 0)),
                        image_type=str(r.get("image_type", "")),
                    )
                )

    shard_images: list[ShardImageRef] = []
    raw_images = raw.get("images") or meta.get("images")
    if isinstance(raw_images, list):
        for img in raw_images:
            if not isinstance(img, dict):
                continue
            image_id = str(img.get("image_id", "")).strip()
            if not image_id:
                continue
            image_type = str(img.get("image_type", "") or "")
            role_raw = str(img.get("role", "") or "")
            shard_images.append(
                ShardImageRef(
                    image_id=image_id,
                    image_type=image_type,
                    role=role_raw or image_type or "image",
                    content_type=str(img.get("content_type", "") or ""),
                    filename=str(img.get("filename", "") or ""),
                    bytes=img.get("bytes"),
                )
            )

    if not shard_images:
        si = meta.get("shard_images")
        if isinstance(si, list):
            for s in si:
                if isinstance(s, dict):
                    shard_images.append(
                        ShardImageRef(
                            image_id=str(s.get("image_id", "")),
                            image_type=str(s.get("image_type", "")),
                            role=str(s.get("role", "")),
                            content_type=str(s.get("content_type", "")),
                            filename=str(s.get("filename", "")),
                            bytes=s.get("bytes"),
                        )
                    )

    return DecoratedPatchSample(
        sample_id=str(
            meta.get("sample_id") or raw.get("id") or raw.get("sample_id", "")
        ),
        inspection_time=parse_inspection_time(meta.get("inspection_time")),
        wafer_key=meta.get("wafer_key", 0),
        defect_id=str(meta.get("defect_id", "")),
        lot_id=str(meta.get("lot_id", "")),
        wafer_x=meta.get("wafer_x", 0),
        wafer_y=meta.get("wafer_y", 0),
        rough_bin=meta.get("rough_bin", 0),
        class_number=meta.get("class_number"),
        review_images=review_images,
        shard_images=shard_images,
        label=str(raw.get("label", "")),
    )


# ── to_sample ──────────────────────────────────────────────────────────


@mapper.register([DecoratedPatchSample, DecoratedPatchSample.ID], [Sample])
def patch_sample_to_sample(obj: PatchSample, *, dataset_id: str = "") -> Sample:
    image_uris: list[str] = []
    for ref in obj.shard_images:
        if ref.image_id:
            image_uris.append(ref.image_id)

    return Sample(
        id=str(uuid4()),
        dataset_id=dataset_id,
        image_uris=image_uris,
        metadata=_patch_sample_to_meta(obj),
    )


# ── to_meta ────────────────────────────────────────────────────────────


def _patch_sample_to_meta(obj: PatchSample) -> dict:
    meta: dict = {}
    meta["sample_id"] = obj.sample_id
    if obj.inspection_time is not None:
        meta["inspection_time"] = obj.inspection_time.isoformat()
    meta["wafer_key"] = obj.wafer_key
    meta["defect_id"] = obj.defect_id
    meta["lot_id"] = obj.lot_id
    meta["wafer_x"] = obj.wafer_x
    meta["wafer_y"] = obj.wafer_y
    meta["rough_bin"] = obj.rough_bin
    if obj.class_number is not None:
        meta["class_number"] = obj.class_number
    if obj.review_images:
        meta["review_images"] = [r.model_dump(mode="json") for r in obj.review_images]
    if obj.shard_images:
        meta["shard_images"] = [s.model_dump(mode="json") for s in obj.shard_images]
    return meta


# ── view adapters ──────────────────────────────────────────────────────


@mapper.register(
    [DecoratedPatchSample, DecoratedPatchSample.ID],
    [ScPatchImageV1Row, ScPatchImageV1Row.view_id],
)
def patch_sample_to_patch_image_v1(
    obj: PatchSample, *, dataset_id: str | None = None
) -> ScPatchImageV1Row:
    images: list[ScImageRef] = []
    if dataset_id:
        ds_q = quote(dataset_id, safe="")
        sid_q = quote(obj.sample_id, safe="")
        for ref in obj.shard_images:
            iid_q = quote(ref.image_id, safe="")
            url = (
                getattr(ref, "access_url", None)
                or f"/api/v1/datasets/{ds_q}/samples/{sid_q}/images/{iid_q}"
            )
            images.append(
                ScImageRef(
                    role=ref.role or ref.image_type or "image",
                    image_id=ref.image_id,
                    image_type=ref.image_type,
                    content_type=ref.content_type,
                    url=url,
                    bytes=ref.bytes,
                )
            )

    return ScPatchImageV1Row(
        sample_id=obj.sample_id,
        inspection_time=obj.inspection_time.isoformat() if obj.inspection_time else "",
        wafer_key=obj.wafer_key,
        defect_id=obj.defect_id,
        wafer_x=obj.wafer_x,
        wafer_y=obj.wafer_y,
        die_x=obj.die_x,
        die_y=obj.die_y,
        rough_bin=obj.rough_bin,
        class_number=obj.class_number,
        images=images,
        review_images=[{"image_id": r.image_id} for r in images if r.role == "review"],
        label=obj.label,
    )


@mapper.register(
    [DecoratedPatchSample, DecoratedPatchSample.ID],
    [ScReviewImageV1Row, ScReviewImageV1Row.view_id],
)
def patch_sample_to_review_image_v1(obj: PatchSample) -> ScReviewImageV1Row:
    return ScReviewImageV1Row(
        sample_id=obj.sample_id,
        inspection_time=obj.inspection_time.isoformat() if obj.inspection_time else "",
        wafer_key=obj.wafer_key,
        defect_id=obj.defect_id,
        wafer_x=obj.wafer_x,
        wafer_y=obj.wafer_y,
        rough_bin=obj.rough_bin,
        class_number=obj.class_number,
        review_images=[r.model_dump(mode="json") for r in obj.review_images],
    )


# ── glue: Sample → view row ───────────────────────────────────────────


@mapper.register(
    [Sample],
    [ScPatchImageV1Row, ScPatchImageV1Row.view_id],
)
def sample_to_patch_image_v1(
    sample: Sample | dict, *, dataset_id: str | None = None
) -> ScPatchImageV1Row:
    obj = from_sample_to_patch_sample(sample)
    return patch_sample_to_patch_image_v1(obj, dataset_id=dataset_id)


@mapper.register(
    [Sample],
    [ScReviewImageV1Row, ScReviewImageV1Row.view_id],
)
def sample_to_review_image_v1(sample: Sample | dict) -> ScReviewImageV1Row:
    obj = from_sample_to_patch_sample(sample)
    return patch_sample_to_review_image_v1(obj)
