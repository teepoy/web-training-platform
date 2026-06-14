from __future__ import annotations

from typing import Any, cast

from app.core.mapper_registry import mapper
from app.shared.api.schemas import Sample

from app.modules.datasets.classification.models import ClassificationSample
from app.modules.datasets.detection.models import BoxV1, DetectionSample
from app.modules.datasets.vqa.models import VQASample
from app.modules.datasets.port.http.schemas import ImageInputV1Row
from app.modules.datasets.views.labeled_image.v1.schemas import LabeledImageV1Row
from app.modules.datasets.views.box_detection.v1.schemas import (
    BoxDetectionV1Row,
    BoxV1Row,
)
from app.modules.datasets.views.qa_input.v1.schemas import QAInputV1Row
from datetime import UTC, datetime

from app.modules.datasets.domain.sample_row import (
    BulkSampleRow,
    SampleRow,
    SampleRowImageRef,
)
from app.modules.sc.views.patch_image.v1.schemas import ScImageRef, ScPatchImageV1Row
from app.modules.sc.views.review_image.v1.schemas import ScReviewImageV1Row


# ════════════════════════════════════════════════════════════════════════
# ClassificationSample
# ════════════════════════════════════════════════════════════════════════


@mapper.register([Sample], [ClassificationSample, ClassificationSample.ID])
def from_sample_to_classification_sample(
    sample: Sample | dict,
) -> ClassificationSample:
    if isinstance(sample, dict):
        label = ""
        ann = sample.get("latest_annotation")
        if isinstance(ann, dict):
            label = str(ann.get("label", ""))
        return ClassificationSample(
            sample_id=str(sample.get("id", sample.get("sample_id", ""))),
            image_uris=cast("list[str]", sample.get("image_uris", [])),
            label=label,
            metadata=cast("dict", sample.get("metadata", {})),
        )
    label = getattr(sample, "label", None)
    return ClassificationSample(
        sample_id=sample.id,
        image_uris=sample.image_uris,
        label=str(label) if label else "",
        metadata=sample.metadata if hasattr(sample, "metadata") else {},
    )


@mapper.register([ClassificationSample, ClassificationSample.ID], [Sample])
def classification_sample_to_sample(obj: ClassificationSample) -> Sample:
    return Sample(
        id=obj.sample_id,
        dataset_id="",
        image_uris=obj.image_uris,
        metadata=obj.metadata,
    )


@mapper.register(
    [ClassificationSample, ClassificationSample.ID],
    [LabeledImageV1Row, "labeled_image_v1"],
)
def classification_sample_to_labeled_image_v1(
    obj: ClassificationSample,
) -> LabeledImageV1Row:
    return LabeledImageV1Row(
        sample_id=obj.sample_id,
        image_uris=obj.image_uris,
        label=obj.label,
    )


@mapper.register(
    [ClassificationSample, ClassificationSample.ID],
    [ImageInputV1Row, "image_input_v1"],
)
def classification_sample_to_image_input_v1(
    obj: ClassificationSample,
) -> ImageInputV1Row:
    return ImageInputV1Row(
        sample_id=obj.sample_id,
        image_uris=obj.image_uris,
    )


# ════════════════════════════════════════════════════════════════════════
# DetectionSample
# ════════════════════════════════════════════════════════════════════════


@mapper.register([Sample], [DetectionSample, DetectionSample.ID])
def from_sample_to_detection_sample(
    sample: Sample | dict,
) -> DetectionSample:
    if isinstance(sample, dict):
        ann = sample.get("latest_annotation")
        ann_value: object = (
            ann.get("annotation_value", []) if isinstance(ann, dict) else []
        )
        boxes: list[BoxV1] = []
        if isinstance(ann_value, list):
            for b in ann_value:
                if isinstance(b, dict):
                    boxes.append(
                        BoxV1(
                            label=str(b.get("label", "")),
                            x=float(b.get("x", 0)),
                            y=float(b.get("y", 0)),
                            width=float(b.get("width", 0)),
                            height=float(b.get("height", 0)),
                        )
                    )
        return DetectionSample(
            sample_id=str(sample.get("id", sample.get("sample_id", ""))),
            image_uris=cast("list[str]", sample.get("image_uris", [])),
            boxes=boxes,
            metadata=cast("dict", sample.get("metadata", {})),
        )
    meta = getattr(sample, "metadata", getattr(sample, "metadata_json", {}))
    return DetectionSample(
        sample_id=sample.id,
        image_uris=sample.image_uris,
        boxes=[],
        metadata=meta if isinstance(meta, dict) else {},
    )


@mapper.register([DetectionSample, DetectionSample.ID], [Sample])
def detection_sample_to_sample(obj: DetectionSample) -> Sample:
    return Sample(
        id=obj.sample_id,
        dataset_id="",
        image_uris=obj.image_uris,
        metadata=obj.metadata,
    )


@mapper.register(
    [DetectionSample, DetectionSample.ID],
    [BoxDetectionV1Row, "box_detection_v1"],
)
def detection_sample_to_box_detection_v1(
    obj: DetectionSample,
) -> BoxDetectionV1Row:
    return BoxDetectionV1Row(
        sample_id=obj.sample_id,
        image_uris=obj.image_uris,
        boxes=[
            BoxV1Row(label=b.label, x=b.x, y=b.y, width=b.width, height=b.height)
            for b in obj.boxes
        ],
        width=obj.width,
        height=obj.height,
    )


@mapper.register(
    [DetectionSample, DetectionSample.ID],
    [ImageInputV1Row, "image_input_v1"],
)
def detection_sample_to_image_input_v1(
    obj: DetectionSample,
) -> ImageInputV1Row:
    return ImageInputV1Row(
        sample_id=obj.sample_id,
        image_uris=obj.image_uris,
    )


# ════════════════════════════════════════════════════════════════════════
# VQASample
# ════════════════════════════════════════════════════════════════════════


@mapper.register([Sample], [VQASample, VQASample.ID])
def from_sample_to_vqa_sample(
    sample: Sample | dict,
) -> VQASample:
    if isinstance(sample, dict):
        meta_raw: object = sample.get("metadata", {})
        metadata: dict = meta_raw if isinstance(meta_raw, dict) else {}
        question = str(metadata.get("question", ""))
        image_uris_raw: object = sample.get("image_uris", [])
        image_uris: list[str] = (
            [str(u) for u in image_uris_raw] if isinstance(image_uris_raw, list) else []
        )
        return VQASample(
            sample_id=str(sample.get("id", sample.get("sample_id", ""))),
            image_uris=image_uris,
            question=question,
            metadata=dict(metadata),
        )
    meta = getattr(sample, "metadata", getattr(sample, "metadata_json", {}))
    question = ""
    if isinstance(meta, dict):
        question = str(meta.get("question", ""))
    return VQASample(
        sample_id=sample.id,
        image_uris=sample.image_uris,
        question=question,
        metadata=meta if isinstance(meta, dict) else {},
    )


@mapper.register([VQASample, VQASample.ID], [Sample])
def vqa_sample_to_sample(obj: VQASample) -> Sample:
    return Sample(
        id=obj.sample_id,
        dataset_id="",
        image_uris=obj.image_uris,
        metadata=obj.metadata,
    )


@mapper.register(
    [VQASample, VQASample.ID],
    [QAInputV1Row, "qa_input_v1"],
)
def vqa_sample_to_qa_input_v1(obj: VQASample) -> QAInputV1Row:
    return QAInputV1Row(
        sample_id=obj.sample_id,
        image_uris=obj.image_uris,
        question=obj.question,
    )


@mapper.register(
    [VQASample, VQASample.ID],
    [ImageInputV1Row, "image_input_v1"],
)
def vqa_sample_to_image_input_v1(obj: VQASample) -> ImageInputV1Row:
    return ImageInputV1Row(
        sample_id=obj.sample_id,
        image_uris=obj.image_uris,
    )


# ════════════════════════════════════════════════════════════════════════
# Glue mappers: Sample → view row (by dataset type)
# ════════════════════════════════════════════════════════════════════════


@mapper.register(
    [Sample],
    [LabeledImageV1Row, "labeled_image_v1"],
)
def sample_to_cls_labeled_image_v1(sample: Sample | dict) -> LabeledImageV1Row:
    return classification_sample_to_labeled_image_v1(
        from_sample_to_classification_sample(sample)
    )


@mapper.register(
    [Sample],
    [ImageInputV1Row, "image_input_v1"],
)
def sample_to_cls_image_input_v1(sample: Sample | dict) -> ImageInputV1Row:
    return classification_sample_to_image_input_v1(
        from_sample_to_classification_sample(sample)
    )


@mapper.register(
    [Sample],
    [BoxDetectionV1Row, "box_detection_v1"],
)
def sample_to_det_box_detection_v1(sample: Sample | dict) -> BoxDetectionV1Row:
    return detection_sample_to_box_detection_v1(from_sample_to_detection_sample(sample))


@mapper.register(
    [Sample],
    [QAInputV1Row, "qa_input_v1"],
)
def sample_to_vqa_qa_input_v1(sample: Sample | dict) -> QAInputV1Row:
    return vqa_sample_to_qa_input_v1(from_sample_to_vqa_sample(sample))


# ════════════════════════════════════════════════════════════════════════
# SampleRow / BulkSampleRow bridge mappers
# ════════════════════════════════════════════════════════════════════════


def _sample_row_to_sample(row: SampleRow, *, dataset_id: str = "") -> Sample:
    """Internal helper: SampleRow → Sample without going through mapper registry.

    Injects ``embedded_bytes`` into ``metadata[\"images\"]`` as
    ``{role: bytes}`` dicts so that downstream SC mappers
    (:func:`~app.modules.sc.domain.mapper.from_sample_to_patch_sample`)
    can resolve image bytes without storage round-trips.
    """
    metadata = dict(row.metadata)
    if row.embedded_bytes:
        images = metadata.setdefault("images", [])
        if not images:
            for key, val in row.embedded_bytes.items():
                if isinstance(val, bytes):
                    role = key.replace("_bytes", "").replace("image", "defective")
                    images.append({"role": role, "image_id": key, "bytes": val})
            metadata["images"] = images

    return Sample(
        id=row.sample_id,
        dataset_id=dataset_id or row.dataset_id,
        image_uris=row.image_uris,
        metadata=metadata,
        ls_task_id=row.ls_task_id,
        created_at=row.created_at if row.created_at is not None else datetime.now(UTC),
    )


@mapper.register([SampleRow, "sample_row"], [Sample])
def sample_row_to_sample(row: SampleRow, *, dataset_id: str = "") -> Sample:
    return _sample_row_to_sample(row, dataset_id=dataset_id)


@mapper.register([BulkSampleRow, "bulk_sample_row"], [Sample])
def bulk_sample_row_to_sample(row: BulkSampleRow, *, dataset_id: str = "") -> Sample:
    metadata: dict[str, object] = dict(row.metadata)
    if row.label:
        metadata["label"] = row.label
    if row.extra:
        for k, v in row.extra.items():
            metadata[k] = v
    return Sample(
        id=row.sample_id,
        dataset_id=dataset_id,
        image_uris=row.image_uris,
        metadata=metadata,
    )


@mapper.register([Sample], [SampleRow, "sample_row"])
def sample_to_sample_row(sample: Sample) -> SampleRow:
    return SampleRow(
        sample_id=sample.id,
        dataset_id=sample.dataset_id,
        image_uris=sample.image_uris,
        metadata=sample.metadata,
        images=None,
        embedded_bytes=None,
        ls_task_id=sample.ls_task_id,
        created_at=sample.created_at,
    )


@mapper.register([dict], [SampleRow, "sample_row"])
def dict_to_sample_row(data: dict) -> SampleRow:
    sample_id = str(data.get("sample_id", data.get("id", "")))
    dataset_id = str(data.get("dataset_id", ""))
    ls_task_id: int | None = data.get("ls_task_id")
    created_at_raw = data.get("created_at")

    raw_uris = data.get("image_uris", [])
    if isinstance(raw_uris, str):
        import json

        raw_uris = json.loads(raw_uris)
    image_uris: list[str] = (
        [str(u) for u in raw_uris] if isinstance(raw_uris, list) else []
    )

    raw_meta = data.get("metadata", {})
    if isinstance(raw_meta, str):
        import json

        raw_meta = json.loads(raw_meta)
    metadata: dict[str, object] = dict(raw_meta) if isinstance(raw_meta, dict) else {}

    images: list[SampleRowImageRef] | None = None
    raw_images = data.get("images")
    if isinstance(raw_images, list) and raw_images:
        images = []
        for img in raw_images:
            if not isinstance(img, dict):
                continue
            img_id = str(img.get("image_id", img.get("id", "")))
            images.append(
                SampleRowImageRef(
                    image_id=img_id,
                    role=str(img.get("role", "")),
                    content_type=str(img.get("content_type", "")),
                    filename=str(img.get("filename", "")),
                    bytes_=img.get("bytes"),
                    access_url=f"/api/v1/samples/{sample_id}/images/{img_id}",
                )
            )

    _embedded: dict[str, bytes] = {}
    for _key, _val in data.items():
        if isinstance(_val, bytes):
            _embedded[_key] = _val

    label: str | None = data.get("label")
    if isinstance(label, str) and label:
        label = label
    else:
        label = None

    return SampleRow(
        sample_id=sample_id,
        dataset_id=dataset_id,
        image_uris=image_uris,
        metadata=metadata,
        images=images,
        embedded_bytes=_embedded if _embedded else None,
        label=label,
        ls_task_id=ls_task_id,
        created_at=created_at_raw,
    )


# ════════════════════════════════════════════════════════════════════════
# Glue mappers: SampleRow → view row (delegates via _sample_row_to_sample)
# ════════════════════════════════════════════════════════════════════════

# --- Datasets view types ---


@mapper.register(
    [SampleRow, "sample_row"],
    [LabeledImageV1Row, "labeled_image_v1"],
)
def sample_row_to_labeled_image_v1(row: SampleRow, **kwargs: Any) -> LabeledImageV1Row:
    ds_id = kwargs.pop("dataset_id", row.dataset_id)
    sample = _sample_row_to_sample(row, dataset_id=ds_id)
    fn = mapper.get_mapper(Sample, LabeledImageV1Row)
    return fn(sample)


@mapper.register(
    [SampleRow, "sample_row"],
    [ImageInputV1Row, "image_input_v1"],
)
def sample_row_to_image_input_v1(row: SampleRow, **kwargs: Any) -> ImageInputV1Row:
    ds_id = kwargs.pop("dataset_id", row.dataset_id)
    sample = _sample_row_to_sample(row, dataset_id=ds_id)
    fn = mapper.get_mapper(Sample, ImageInputV1Row)
    return fn(sample)


@mapper.register(
    [SampleRow, "sample_row"],
    [BoxDetectionV1Row, "box_detection_v1"],
)
def sample_row_to_box_detection_v1(row: SampleRow, **kwargs: Any) -> BoxDetectionV1Row:
    ds_id = kwargs.pop("dataset_id", row.dataset_id)
    sample = _sample_row_to_sample(row, dataset_id=ds_id)
    fn = mapper.get_mapper(Sample, BoxDetectionV1Row)
    return fn(sample)


@mapper.register(
    [SampleRow, "sample_row"],
    [QAInputV1Row, "qa_input_v1"],
)
def sample_row_to_qa_input_v1(row: SampleRow, **kwargs: Any) -> QAInputV1Row:
    ds_id = kwargs.pop("dataset_id", row.dataset_id)
    sample = _sample_row_to_sample(row, dataset_id=ds_id)
    fn = mapper.get_mapper(Sample, QAInputV1Row)
    return fn(sample)


# --- SC view types (direct mapping: SampleRow → view row, no intermediate types) ---


def _embedded_bytes_to_sc_image_refs(
    row: SampleRow,
    *,
    dataset_id: str = "",
) -> list[ScImageRef]:
    """Build ``ScImageRef`` list from ``row.images`` (v2) and/or ``row.embedded_bytes`` (v1)."""
    from urllib.parse import quote

    refs: list[ScImageRef] = []
    sid_q = quote(row.sample_id, safe="")
    ds_q = quote(dataset_id, safe="") if dataset_id else ""
    ds_param = f"?dataset_id={ds_q}" if ds_q else ""

    if row.images:
        for img in row.images:
            iid_q = quote(img.image_id, safe="")
            url = img.access_url or f"/api/v1/samples/{sid_q}/images/{iid_q}{ds_param}"
            refs.append(
                ScImageRef(
                    role=img.role or img.image_id,
                    image_id=img.image_id,
                    image_type=img.image_type or img.content_type,
                    content_type=img.content_type,
                    url=url,
                    bytes=img.bytes_,
                )
            )

    if row.embedded_bytes:
        for key, val in row.embedded_bytes.items():
            if not isinstance(val, bytes):
                continue
            role = key.replace("_bytes", "").replace("image", "defective")
            iid_q = quote(key, safe="")
            refs.append(
                ScImageRef(
                    role=role,
                    image_id=key,
                    image_type="",
                    content_type="",
                    url=f"/api/v1/samples/{sid_q}/images/{iid_q}{ds_param}",
                    bytes=val,
                )
            )

    return refs


def _sample_row_meta_to_sc_fields(
    row: SampleRow,
) -> dict[str, Any]:
    """Extract SC-specific fields from ``SampleRow.metadata``.

    Returns a dict with keys matching ``ScPatchImageV1Row``
    constructor parameters.
    """
    from app.modules.sc.domain.models import parse_inspection_time

    meta: dict[str, Any] = row.metadata if isinstance(row.metadata, dict) else {}

    inspection_time = parse_inspection_time(meta.get("inspection_time"))
    return {
        "inspection_time": (
            inspection_time.isoformat() if inspection_time is not None else ""
        ),
        "wafer_key": meta.get("wafer_key", 0) or 0,
        "defect_id": str(meta.get("sample_id", "") or meta.get("defect_id", "") or ""),
        "wafer_x": meta.get("wafer_x", 0) or 0,
        "wafer_y": meta.get("wafer_y", 0) or 0,
        "rough_bin": meta.get("rough_bin", 0) or 0,
        "class_number": meta.get("class_number"),
    }


@mapper.register(
    [SampleRow, "sample_row"],
    [ScPatchImageV1Row, ScPatchImageV1Row.view_id],
)
def sample_row_to_sc_patch_image_v1(row: SampleRow, **kwargs: Any) -> ScPatchImageV1Row:
    ds_id = kwargs.pop("dataset_id", row.dataset_id)
    die_x = kwargs.pop("die_x", 0)
    die_y = kwargs.pop("die_y", 0)
    label = row.latest_label or row.label or ""
    pred = row.latest_prediction or {}
    predicted_label = str(pred.get("predicted_label") or "")
    confidence = pred.get("confidence")
    if confidence is not None:
        confidence = float(confidence)
    sc_fields = _sample_row_meta_to_sc_fields(row)
    images = _embedded_bytes_to_sc_image_refs(row, dataset_id=ds_id)
    review_images: list[dict[str, Any]] = [
        {"image_id": r.image_id} for r in images if r.role == "review"
    ]
    return ScPatchImageV1Row(
        sample_id=row.sample_id,
        die_x=die_x,
        die_y=die_y,
        images=images,
        review_images=review_images,
        label=label,
        predicted_label=predicted_label,
        confidence=confidence,
        **sc_fields,
    )


@mapper.register(
    [SampleRow, "sample_row"],
    [ScReviewImageV1Row, ScReviewImageV1Row.view_id],
)
def sample_row_to_sc_review_image_v1(
    row: SampleRow, **kwargs: Any
) -> ScReviewImageV1Row:
    meta: dict[str, Any] = row.metadata if isinstance(row.metadata, dict) else {}
    sc_fields = _sample_row_meta_to_sc_fields(row)
    review_images: list[dict[str, Any]] = meta.get("review_images", []) or []
    return ScReviewImageV1Row(
        sample_id=row.sample_id,
        review_images=review_images,
        **sc_fields,
    )
