from __future__ import annotations

import asyncio
import mimetypes
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

import polars as pl

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.modules.auth.port.http.deps import get_current_org, get_current_user
from app.modules.sc.port.http.deps import (
    DatasetPayloadStoreDep,
    ScImageFetcherDep,
    ScImportServiceDep,
    PrefectClientDep,
    ScPlotPointsServiceDep,
    ScSpriteServiceDep,
    ScUpstreamReaderDep,
)
from app.modules.sc.app.services.sc_plot_points_service import (
    ScPlotPointsNotFoundError,
    ScPlotPointsRejectedError,
    filter_box_defect_ids,
)
from app.modules.sc.proto_adapter import (
    make_class_list_pb,
    make_wafer_map_response_pb,
)
from app.modules.sc.schemas import (
    ScBoxFilterRequest,
    ScBoxFilterResponse,
    ScInspectionReviewImagesResponse,
    ScImportRequest,
    ScImportResponse,
    ScInspectionListResponse,
    ScInspectionSummaryItem,
    ScReviewImageItem,
    ScReviewImagesByDefectItem,
    ScSampleTableRow,
    ScSampleTableRowsRequest,
    ScSampleTableRowsResponse,
)
from app.shared.api.schemas import Organization, User
from app.shared.sse.emit import emit_sse
from app.shared.sse.events import DoneEvent, ScErrorEvent, ScProgressEvent, SSEEvent
from app.modules.sc.domain.models import (
    ScImageCacheError,
    ScImageNotFoundError,
    ScImageUpstreamError,
)

router = APIRouter(prefix="/sc", tags=["sc"])


# Inspection API — reads through the SC upstream reader Protocol


MAX_INSPECTION_RANGE_DAYS = 365


@router.get("/inspections")
async def get_inspections(
    upstream_reader: ScUpstreamReaderDep,
    start_time: datetime = Query(),
    end_time: datetime = Query(),
) -> ScInspectionListResponse:
    if end_time - start_time > timedelta(days=MAX_INSPECTION_RANGE_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"Time range must not exceed {MAX_INSPECTION_RANGE_DAYS} days",
        )

    records_lf = await upstream_reader.list_inspections(start_time, end_time)
    records_df = await records_lf.collect_async()

    items: list[ScInspectionSummaryItem] = []
    for row in records_df.to_dicts():
        insp_dt = row["inspection_time"]
        if isinstance(insp_dt, datetime):
            insp_str = insp_dt.isoformat()
        else:
            insp_str = str(insp_dt)
        items.append(
            ScInspectionSummaryItem(
                inspection_time=insp_str,
                wafer_key=row["wafer_key"],
                lot_id=row["lot_id"],
                wafer_id=row["wafer_id"],
                center_x=row["center_x"],
                center_y=row["center_y"],
                origin_x=row["origin_x"],
                origin_y=row["origin_y"],
                die_size_x=row["die_size_x"],
                die_size_y=row["die_size_y"],
                layer_id=row["layer_id"],
                eqp_id=row["inspect_equip_id"],
                recipe_id=row["recipe_id"],
                defects=row["defects"],
                images=row["images"],
                device=row["device"],
            )
        )

    resp = ScInspectionListResponse(items=items, total=len(items))
    return resp


def _normalize_inspection_time(value: str) -> datetime:
    """Parse inspection_time as ISO string or epoch (seconds / milliseconds).

    Epoch heuristic (applied only when the string is all decimal digits):
    * ``abs(ts) >= 10**12`` → treat as milliseconds
    * otherwise → treat as seconds

    Returns a timezone-aware UTC datetime.
    """
    # 1. Try ISO 8601 first
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    # 2. Digit-only → epoch
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        try:
            ts = int(value)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid epoch-like timestamp: {value}"
            )
        if abs(ts) >= 10**12:
            ts = ts / 1000.0  # milliseconds → seconds
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, OverflowError):
            raise HTTPException(
                status_code=400, detail=f"Timestamp out of range: {value}"
            )

    raise HTTPException(status_code=400, detail=f"Invalid datetime format: {value}")


def _parse_inspection_time(value: str) -> datetime:
    return _normalize_inspection_time(value)


@router.get(
    "/inspections/{inspection_time}/{wafer_key}/map-points",
    responses={
        200: {
            "description": "Return unified aggregated map protobuf (wafer + die + reticle)",
            "content": {
                "application/x-protobuf": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def get_inspection_map_points(
    upstream_reader: ScUpstreamReaderDep,
    inspection_time: str,
    wafer_key: int,
    reticle_x_die_count: int = Query(default=10, alias="reticleXDieCount", ge=1),
    reticle_y_die_count: int = Query(default=10, alias="reticleYDieCount", ge=1),
    reticle_x_die_shift: int = Query(default=0, alias="reticleXDieShift"),
    reticle_y_die_shift: int = Query(default=0, alias="reticleYDieShift"),
    sampled: bool = Query(default=False),
    grid_size_nm: int = Query(default=600, ge=1, alias="gridSizeNm"),
    zoom_x: int | None = Query(default=None, alias="zoomX"),
    zoom_y: int | None = Query(default=None, alias="zoomY"),
    zoom_w: int | None = Query(default=None, alias="zoomW"),
    zoom_h: int | None = Query(default=None, alias="zoomH"),
    mode: Literal["wafer", "die", "reticle"] | None = Query(default=None),
):
    """Unified aggregated map endpoint for Preview mode.

    With *mode*, returns only the requested map point array. Omitting it keeps
    the legacy unified response for compatibility.
    When *sampled* is true, each map type is grid-downsampled independently;
    *total* still reports the full defect count.
    """
    insp_dt = _parse_inspection_time(inspection_time)

    inspection = await upstream_reader.get_inspection(insp_dt, wafer_key)
    if inspection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Inspection not found: {inspection_time}/{wafer_key}",
        )

    samples_lf = await upstream_reader.list_samples(
        insp_dt,
        wafer_key,
        offset=0,
        count=1_000_000,
        reticle_size_x=reticle_x_die_count,
        reticle_size_y=reticle_y_die_count,
        reticle_offset_x=reticle_x_die_shift,
        reticle_offset_y=reticle_y_die_shift,
    )
    df = await samples_lf.collect_async()
    df = df.with_columns((pl.col("images") > 0).cast(pl.Int32).alias("has_review"))
    body = make_wafer_map_response_pb(
        df,
        wafer_key=wafer_key,
        wafer_radius_nm=150_000_000,
        center_x=inspection.center_x,
        center_y=inspection.center_y,
        origin_x=inspection.origin_x,
        origin_y=inspection.origin_y,
        die_size_x=inspection.die_size_x,
        die_size_y=inspection.die_size_y,
        reticle_x_die_count=reticle_x_die_count,
        reticle_y_die_count=reticle_y_die_count,
        sampled=sampled,
        target_resolution=grid_size_nm,
        zoom_x=zoom_x,
        zoom_y=zoom_y,
        zoom_w=zoom_w,
        zoom_h=zoom_h,
        map_mode=mode,
    )
    return Response(content=body, media_type="application/x-protobuf")


@router.get(
    "/inspections/{inspection_time}/{wafer_key}/class-list",
    responses={
        200: {
            "description": "Return compact SC class/bin defect-id lists",
            "content": {
                "application/x-protobuf": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def get_inspection_class_list(
    upstream_reader: ScUpstreamReaderDep,
    inspection_time: str,
    wafer_key: int,
) -> Response:
    insp_dt = _parse_inspection_time(inspection_time)
    inspection = await upstream_reader.get_inspection(insp_dt, wafer_key)
    if inspection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Inspection not found: {inspection_time}/{wafer_key}",
        )
    samples_lf = await upstream_reader.list_samples(
        insp_dt,
        wafer_key,
        offset=0,
        count=1_000_000,
    )
    df = await samples_lf.select(
        "defect_id",
        "class_number",
        "rough_bin",
    ).collect_async()
    return Response(
        content=make_class_list_pb(df),
        media_type="application/x-protobuf",
    )


@router.post(
    "/inspections/{inspection_time}/{wafer_key}/box-filter",
    response_model=ScBoxFilterResponse,
)
async def filter_inspection_box(
    upstream_reader: ScUpstreamReaderDep,
    inspection_time: str,
    wafer_key: int,
    payload: ScBoxFilterRequest,
) -> ScBoxFilterResponse:
    insp_dt = _parse_inspection_time(inspection_time)
    inspection = await upstream_reader.get_inspection(insp_dt, wafer_key)
    if inspection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Inspection not found: {inspection_time}/{wafer_key}",
        )
    samples_lf = await upstream_reader.list_samples(
        insp_dt,
        wafer_key,
        offset=0,
        count=1_000_000,
        reticle_size_x=payload.reticle_x_die_count,
        reticle_size_y=payload.reticle_y_die_count,
        reticle_offset_x=payload.reticle_x_die_shift,
        reticle_offset_y=payload.reticle_y_die_shift,
    )
    try:
        defect_ids = await filter_box_defect_ids(
            samples_lf,
            mode=payload.mode,
            x=payload.x,
            y=payload.y,
            width=payload.width,
            height=payload.height,
        )
    except ScPlotPointsRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScBoxFilterResponse(defect_ids=defect_ids, total=len(defect_ids))


@router.get(
    "/datasets/{dataset_id}/plot-points",
    responses={
        200: {
            "description": "Return SC sparse plot point arrays as WaferMapResponse protobuf",
            "content": {
                "application/x-protobuf": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def get_sc_dataset_plot_points(
    dataset_id: str,
    service: ScPlotPointsServiceDep,
    request: Request,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    sampled: bool = Query(default=True),
    target_resolution: int = Query(default=600, alias="targetResolution", ge=1),
    reticle_x_die_count: int = Query(default=3, alias="reticleXDieCount", ge=1),
    reticle_y_die_count: int = Query(default=5, alias="reticleYDieCount", ge=1),
    reticle_x_die_shift: int = Query(default=0, alias="reticleXDieShift"),
    reticle_y_die_shift: int = Query(default=0, alias="reticleYDieShift"),
) -> Response:
    try:
        body = await service.build_plot_points_response(
            dataset_id,
            org.id,
            sampled=sampled,
            target_resolution=target_resolution,
            reticle_x_die_count=reticle_x_die_count,
            reticle_y_die_count=reticle_y_die_count,
            reticle_x_die_shift=reticle_x_die_shift,
            reticle_y_die_shift=reticle_y_die_shift,
        )
    except ScPlotPointsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScPlotPointsRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=body, media_type="application/x-protobuf")


@router.get(
    "/datasets/{dataset_id}/class-list",
    responses={
        200: {
            "description": "Return compact SC class/bin/prediction/label defect-id lists",
            "content": {
                "application/x-protobuf": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def get_sc_dataset_class_list(
    dataset_id: str,
    service: ScPlotPointsServiceDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    try:
        body = await service.build_class_list_response(dataset_id, org.id)
    except ScPlotPointsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScPlotPointsRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=body, media_type="application/x-protobuf")


@router.post(
    "/datasets/{dataset_id}/box-filter",
    response_model=ScBoxFilterResponse,
)
async def filter_sc_dataset_box(
    dataset_id: str,
    payload: ScBoxFilterRequest,
    service: ScPlotPointsServiceDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ScBoxFilterResponse:
    try:
        defect_ids = await service.filter_dataset_box(
            dataset_id,
            org.id,
            mode=payload.mode,
            x=payload.x,
            y=payload.y,
            width=payload.width,
            height=payload.height,
            reticle_x_die_count=payload.reticle_x_die_count,
            reticle_y_die_count=payload.reticle_y_die_count,
            reticle_x_die_shift=payload.reticle_x_die_shift,
            reticle_y_die_shift=payload.reticle_y_die_shift,
        )
    except ScPlotPointsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScPlotPointsRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScBoxFilterResponse(defect_ids=defect_ids, total=len(defect_ids))


@router.get(
    "/inspections/{inspection_time}/{wafer_key}/review-images",
    response_model=ScInspectionReviewImagesResponse,
)
async def get_inspection_review_images(
    upstream_reader: ScUpstreamReaderDep,
    inspection_time: str,
    wafer_key: int,
) -> ScInspectionReviewImagesResponse:
    insp_dt = _parse_inspection_time(inspection_time)
    inspection = await upstream_reader.get_inspection(insp_dt, wafer_key)
    if inspection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Inspection not found: {inspection_time}/{wafer_key}",
        )

    review_lf = await upstream_reader.list_review_images(insp_dt, wafer_key)
    review_df = await review_lf.collect_async()
    items: list[ScReviewImagesByDefectItem] = []
    if len(review_df) > 0:
        for (defect_id,), group in review_df.group_by("defect_id"):
            review_images = [
                ScReviewImageItem(
                    image_name=row["image_filespec"],
                    image_id=row["image_id"],
                    image_type=row["image_type"],
                )
                for row in group.to_dicts()
            ]
            items.append(
                ScReviewImagesByDefectItem(
                    defect_id=str(defect_id),
                    review_images=review_images,
                )
            )
    return ScInspectionReviewImagesResponse(items=items, total=len(items))


@router.post(
    "/inspections/{inspection_time}/{wafer_key}/sample-table-rows",
    response_model=ScSampleTableRowsResponse,
)
async def get_inspection_sample_table_rows(
    payload: ScSampleTableRowsRequest,
    upstream_reader: ScUpstreamReaderDep,
    inspection_time: str,
    wafer_key: int,
) -> ScSampleTableRowsResponse:
    insp_dt = _parse_inspection_time(inspection_time)
    inspection = await upstream_reader.get_inspection(insp_dt, wafer_key)
    if inspection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Inspection not found: {inspection_time}/{wafer_key}",
        )

    defect_ids = payload.defect_ids
    page = payload.page
    page_size = payload.page_size

    requested = list(dict.fromkeys(defect_ids)) if defect_ids else None
    requested_set = set(requested) if requested else None

    if requested_set is not None:
        max_defects = max(inspection.defects, 100_000)
        samples_lf = await upstream_reader.list_samples(
            insp_dt,
            wafer_key,
            offset=0,
            count=max_defects,
        )
        samples_df = await samples_lf.collect_async()
        samples_df = samples_df.filter(
            pl.col("defect_id").cast(pl.Utf8).is_in(requested_set)
        )
        total_matched = len(samples_df)
        page_df = samples_df.slice(page * page_size, page_size)
    else:
        total_matched = inspection.defects
        samples_lf = await upstream_reader.list_samples(
            insp_dt,
            wafer_key,
            offset=page * page_size,
            count=page_size,
        )
        page_df = await samples_lf.collect_async()
    matched: list[ScSampleTableRow] = [
        ScSampleTableRow(
            defect_id=str(row["defect_id"]),
            rough_bin=row["rough_bin"],
            class_number=row.get("class_number"),
        )
        for row in page_df.to_dicts()
    ]

    if requested is not None:
        order_map = {row.defect_id: row for row in matched}
        matched = [order_map[did] for did in requested if did in order_map]

    return ScSampleTableRowsResponse(items=matched, total=total_matched)


VALID_IMAGE_TYPES = {
    "template",
    "defective",
    "review",
    "difference",
    "PATCH_TEMPLATE",
    "PATCH_DEFECTIVE",
    "PATCH_DIFFERENCE",
    "REVIEW_HIGH_MAG",
}
REVIEW_IMAGE_TYPE = "review"


def _sanitize_path_component(value: str) -> None:
    import re

    if re.search(r"[/\\\.\.]", value):
        raise HTTPException(status_code=400, detail=f"Invalid path component: {value}")


@router.get(
    "/images/{inspection_time}/{wafer_key}/{defect_id}/{image_type}",
    response_class=Response,
)
async def serve_patch_image(
    inspection_time: str,
    wafer_key: int,
    defect_id: str,
    image_type: str,
    image_fetcher: ScImageFetcherDep,
    s3_path: str | None = Query(None),
    review_image_id: int | None = Query(None),
):
    _sanitize_path_component(inspection_time)
    _sanitize_path_component(defect_id)
    if image_type not in VALID_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image_type: {image_type}. "
            f"Must be one of {sorted(VALID_IMAGE_TYPES)}",
        )
    if image_type == REVIEW_IMAGE_TYPE and review_image_id is None:
        raise HTTPException(
            status_code=400,
            detail="review_image_id is required when image_type is 'review'",
        )

    normalized_time = _normalize_inspection_time(inspection_time).isoformat()

    try:
        data = await image_fetcher.get_image_bytes(
            inspection_time=normalized_time,
            wafer_key=wafer_key,
            defect_id=defect_id,
            image_type=image_type,
            s3_path=s3_path,
            review_image_id=review_image_id,
        )
    except ScImageNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Image not found: {defect_id}/{image_type}"
        )
    except ScImageUpstreamError:
        raise HTTPException(status_code=502, detail="image upstream unavailable")
    except ScImageCacheError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")

    media_type, _ = mimetypes.guess_type(f"{defect_id}_{image_type}.png")
    if media_type is None:
        media_type = "image/png"

    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=1200",
        },
    )


# ── Sprite endpoints ──────────────────────────────────────────────────────


@router.get(
    "/sprites/patch/{inspection_time}/{wafer_key}/{defect_id}",
    response_class=Response,
)
async def get_patch_sprite(
    inspection_time: str,
    wafer_key: int,
    defect_id: str,
    sprite_service: ScSpriteServiceDep,
    cell_size: int = Query(default=64, ge=16, le=512),
):
    _sanitize_path_component(inspection_time)
    _sanitize_path_component(defect_id)
    normalized_time = _normalize_inspection_time(inspection_time).isoformat()

    try:
        png_bytes = await sprite_service.build_patch_sprite(
            inspection_time=normalized_time,
            wafer_key=wafer_key,
            defect_id=defect_id,
            cell_size=cell_size,
        )
    except ScImageNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Image not found for sprite: {defect_id}"
        )
    except ScImageUpstreamError:
        raise HTTPException(status_code=502, detail="image upstream unavailable")
    except ScImageCacheError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=1200"},
    )


@router.get(
    "/sprites/review/{inspection_time}/{wafer_key}/{defect_id}",
    response_class=Response,
)
async def get_review_sprite(
    inspection_time: str,
    wafer_key: int,
    defect_id: str,
    sprite_service: ScSpriteServiceDep,
    review_count: int = Query(default=3, ge=1, le=20),
    cell_size: int = Query(default=224, ge=16, le=512),
):
    _sanitize_path_component(inspection_time)
    _sanitize_path_component(defect_id)
    normalized_time = _normalize_inspection_time(inspection_time).isoformat()

    try:
        png_bytes = await sprite_service.build_review_sprite(
            inspection_time=normalized_time,
            wafer_key=wafer_key,
            defect_id=defect_id,
            review_count=review_count,
            cell_size=cell_size,
        )
    except ScImageNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Image not found for sprite: {defect_id}"
        )
    except ScImageUpstreamError:
        raise HTTPException(status_code=502, detail="image upstream unavailable")
    except ScImageCacheError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=1200"},
    )


@router.get(
    "/sprites/patch-batch/{inspection_time}/{wafer_key}",
    response_class=Response,
)
async def get_patch_batch_sprite(
    inspection_time: str,
    wafer_key: int,
    sprite_service: ScSpriteServiceDep,
    defect_ids: list[str] = Query(min_length=1, max_length=200),
    cell_size: int = Query(default=64, ge=16, le=512),
):
    _sanitize_path_component(inspection_time)
    normalized_time = _normalize_inspection_time(inspection_time).isoformat()

    try:
        png_bytes = await sprite_service.build_patch_batch_sprite(
            inspection_time=normalized_time,
            wafer_key=wafer_key,
            defect_ids=defect_ids,
            cell_size=cell_size,
        )
    except ScImageNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found for batch sprite")
    except ScImageUpstreamError:
        raise HTTPException(status_code=502, detail="image upstream unavailable")
    except ScImageCacheError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=1200"},
    )


@router.get(
    "/sprites/review-batch/{inspection_time}/{wafer_key}",
    response_class=Response,
)
async def get_review_batch_sprite(
    inspection_time: str,
    wafer_key: int,
    sprite_service: ScSpriteServiceDep,
    defect_ids: list[str] = Query(min_length=1, max_length=200),
    review_count: int = Query(default=3, ge=1, le=20),
    cell_size: int = Query(default=224, ge=16, le=512),
):
    _sanitize_path_component(inspection_time)
    normalized_time = _normalize_inspection_time(inspection_time).isoformat()

    try:
        png_bytes = await sprite_service.build_review_batch_sprite(
            inspection_time=normalized_time,
            wafer_key=wafer_key,
            defect_ids=defect_ids,
            review_count=review_count,
            cell_size=cell_size,
        )
    except ScImageNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found for batch sprite")
    except ScImageUpstreamError:
        raise HTTPException(status_code=502, detail="image upstream unavailable")
    except ScImageCacheError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=1200"},
    )


TERMINAL_FAILED_STATES = frozenset({"CRASHED", "FAILED", "CANCELLED"})


def _prefect_state_type(flow_run: Any) -> str:
    if isinstance(flow_run, dict):
        return str(flow_run.get("state_type", ""))
    return getattr(flow_run, "state_type", "")


def _prefect_state_message(flow_run: Any) -> str | None:
    if isinstance(flow_run, dict):
        return flow_run.get("state_message")
    return getattr(flow_run, "state_message", None)


def _prefect_state_data(flow_run: Any, key: str) -> object:
    if isinstance(flow_run, dict):
        data = flow_run.get("state", {}).get("data", {})
        if isinstance(data, dict):
            return data.get(key)
        return None
    state = getattr(flow_run, "state", {})
    if isinstance(state, dict):
        data_obj = state.get("data", {})
    else:
        data_obj = getattr(state, "data", {}) if state else {}
    if isinstance(data_obj, dict):
        return data_obj.get(key)
    return None


def _prefect_parameter(flow_run: Any, key: str) -> object:
    if isinstance(flow_run, dict):
        parameters = flow_run.get("parameters", {})
        if isinstance(parameters, dict):
            return parameters.get(key)
        return None
    parameters = getattr(flow_run, "parameters", {})
    if isinstance(parameters, dict):
        return parameters.get(key)
    return None


@router.get("/import/{flow_run_id}/stream")
async def stream_sc_import_progress(
    flow_run_id: str,
    request: Request,
    prefect_client: PrefectClientDep,
    payload_store: DatasetPayloadStoreDep,
    requested_dataset_id: str | None = Query(None, alias="dataset_id"),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    async def event_generator():
        dataset_open_emitted = False
        while True:
            if await request.is_disconnected():
                break
            try:
                flow_run = await prefect_client.get_flow_run(flow_run_id)
            except HTTPException as e:
                detail = str(e.detail)
                if e.status_code == 404:
                    detail = "import flow run not found"
                yield emit_sse(SSEEvent(ScErrorEvent(event_type="error", error=detail)))
                return

            state_type = _prefect_state_type(flow_run)
            state_message = _prefect_state_message(flow_run)
            dataset_id = requested_dataset_id or _prefect_parameter(
                flow_run, "dataset_id"
            )
            imported_count = 0
            if isinstance(dataset_id, str):
                try:
                    payload_store.invalidate_manifest(dataset_id, org.id)
                    manifest = await payload_store.get_manifest(dataset_id, org.id)
                    imported_count = manifest.total_rows
                except (FileNotFoundError, KeyError):
                    imported_count = 0
            if state_type == "COMPLETED":
                state_dataset_id = _prefect_state_data(flow_run, "dataset_id")
                if isinstance(state_dataset_id, str):
                    dataset_id = state_dataset_id
                yield emit_sse(
                    SSEEvent(
                        DoneEvent(
                            event_type="done",
                            dataset_id=dataset_id
                            if isinstance(dataset_id, str)
                            else None,
                        )
                    )
                )
                return
            if state_type in TERMINAL_FAILED_STATES:
                error = state_message or f"import flow run {state_type.lower()}"
                yield emit_sse(
                    SSEEvent(
                        ScErrorEvent(
                            event_type="error",
                            flow_run_id=flow_run_id,
                            status=state_type.lower(),
                            error=error,
                        )
                    )
                )
                return
            yield emit_sse(
                SSEEvent(
                    ScProgressEvent(
                        event_type="progress",
                        flow_run_id=flow_run_id,
                        status=state_type.lower(),
                        dataset_id=dataset_id
                        if isinstance(dataset_id, str)
                        and imported_count > 0
                        and not dataset_open_emitted
                        else None,
                        imported_count=imported_count,
                    )
                )
            )
            if imported_count > 0:
                dataset_open_emitted = True
            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentOrgDep = Annotated[Organization, Depends(get_current_org)]


@router.post("/import", response_model=ScImportResponse, status_code=202)
async def start_sc_import(
    payload: ScImportRequest,
    sc_import_service: ScImportServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> ScImportResponse | JSONResponse:
    status, flow_run_id = await sc_import_service.submit_import(
        source_inspection_time=payload.source_inspection_time,
        source_wafer_key=payload.source_wafer_key,
        dataset_name=payload.dataset_name,
        storage_mode=payload.storage_mode,
        org_id=org.id,
        filters=payload.filters,
        label_space=payload.label_space,
        max_rows=payload.max_rows,
        force_prefect_flow=payload.force_prefect_flow,
    )
    if status.status == "failed":
        return JSONResponse(
            content=ScImportResponse(
                flow_run_id=None,
                status="failed",
                error=status.error,
            ).model_dump(mode="json"),
            status_code=200,
        )
    return ScImportResponse(
        flow_run_id=flow_run_id,
        status=status.status,
        dataset_id=status.dataset_id,
        imported_count=status.imported_count,
        error=status.error,
    )
