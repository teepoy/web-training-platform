from __future__ import annotations

import asyncio
import hashlib
import json
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

import polars as pl

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.modules.auth.port.http.deps import get_current_org, get_current_user
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.datasets.port.http.deps import (
    DatasetServiceDep,
    get_repository,
)
from app.modules.sc.port.http.deps import (
    DatasetPayloadStoreDep,
    ScDatasetReaderDep,
    ScDatasetStoreDep,
    ScImageFetcherDep,
    ScImportServiceDep,
    PrefectClientDep,
    ScPlotPointsServiceDep,
    ScUpstreamReaderDep,
)
from app.modules.sc.app.services.sc_plot_points_service import (
    ScPlotPointsNotFoundError,
    ScPlotPointsRejectedError,
    _apply_sample_filters,
    encode_defect_ids_int32le,
    filter_box_defect_ids,
    sorted_defect_ids_from_lazyframe,
)
from app.modules.sc.proto_adapter import (
    make_wafer_map_response_pb,
)
from app.modules.sc.schemas import (
    ScBoxFilterRequest,
    ScBoxFilterResponse,
    ScBulkAnnotationRequest,
    ScBulkAnnotationResponse,
    ScFilterParams,
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
from app.shared.api.schemas import Annotation, Organization, User
from app.shared.sse.emit import emit_sse
from app.shared.sse.events import DoneEvent, ScErrorEvent, ScProgressEvent, SSEEvent

router = APIRouter(prefix="/sc", tags=["sc"])

_SAMPLE_TABLE_COLUMNS = {
    "defect_id": "defect_id",
    "rough_bin": "rough_bin",
    "class_number": "class_number",
    "test_id": "test_id",
    "wafer_x": "wafer_x",
    "wafer_y": "wafer_y",
    "index_x": "index_x",
    "index_y": "index_y",
    "die_x": "index_x",
    "die_y": "index_y",
    "size_x": "size_x",
    "size_y": "size_y",
    "size_d": "size_d",
    "area": "area",
    "final_bin": "final_bin",
    "manual_bin": "manual_bin",
    "adder": "adder",
    "cluster_id": "cluster",
    "kill_ratio": "kill_ratio",
}

_SAMPLE_TABLE_CACHE_DIR = (
    Path(tempfile.gettempdir()) / "web-training-platform" / "sc-sample-table-cache"
)

_TOP_LEVEL_FILTER_COLUMNS = {
    "lot_id": "lot_id",
    "layer_id": "layer_id",
    "device": "device",
    "eqp_id": "inspect_equip_id",
}


# Inspection API — reads through the SC upstream reader Protocol


MAX_INSPECTION_RANGE_DAYS = 365


def get_sc_filter_params(
    class_numbers: Annotated[list[int] | None, Query()] = None,
    rough_bins: Annotated[list[int] | None, Query()] = None,
    predictions: Annotated[list[str] | None, Query()] = None,
    annotations: Annotated[list[str] | None, Query()] = None,
    test_ids: Annotated[list[int] | None, Query()] = None,
    adders: Annotated[list[int] | None, Query()] = None,
    cluster_ids: Annotated[list[int] | None, Query()] = None,
    legend_group_by: Annotated[
        Literal["class", "bin", "annotation", "prediction"] | None,
        Query(),
    ] = None,
) -> ScFilterParams:
    return ScFilterParams(
        class_numbers=class_numbers,
        rough_bins=rough_bins,
        predictions=predictions,
        annotations=annotations,
        test_ids=test_ids,
        adders=adders,
        cluster_ids=cluster_ids,
        legend_group_by=legend_group_by,
    )


@router.get("/inspections")
async def get_inspections(
    upstream_reader: ScUpstreamReaderDep,
    start_time: datetime = Query(),
    end_time: datetime = Query(),
    lot_id: Annotated[str | None, Query()] = None,
    layer_id: Annotated[str | None, Query()] = None,
    device: Annotated[str | None, Query()] = None,
    eqp_id: Annotated[str | None, Query()] = None,
) -> ScInspectionListResponse:
    if end_time - start_time > timedelta(days=MAX_INSPECTION_RANGE_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"Time range must not exceed {MAX_INSPECTION_RANGE_DAYS} days",
        )

    records_lf = await upstream_reader.list_inspections(
        start_time, end_time, lot_id, None, layer_id, device
    )
    records_lf = _apply_top_level_inspection_filters(
        records_lf,
        lot_id=lot_id,
        layer_id=layer_id,
        device=device,
        eqp_id=eqp_id,
    )
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


def _parse_top_level_condition(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts or "*" in parts:
        return None
    return parts


def _condition_expr(column: str, values: list[str]) -> pl.Expr:
    exprs: list[pl.Expr] = []
    for value in values:
        if "*" in value:
            regex = "^" + ".*".join(re.escape(part) for part in value.split("*")) + "$"
            exprs.append(pl.col(column).cast(pl.Utf8).str.contains(regex))
        else:
            exprs.append(pl.col(column).cast(pl.Utf8) == value)
    combined = exprs[0]
    for expr in exprs[1:]:
        combined = combined | expr
    return combined


def _apply_top_level_inspection_filters(
    records_lf: pl.LazyFrame,
    *,
    lot_id: str | None,
    layer_id: str | None,
    device: str | None,
    eqp_id: str | None,
) -> pl.LazyFrame:
    filters = {
        "lot_id": lot_id,
        "layer_id": layer_id,
        "device": device,
        "eqp_id": eqp_id,
    }
    for field, raw in filters.items():
        values = _parse_top_level_condition(raw)
        column = _TOP_LEVEL_FILTER_COLUMNS[field]
        if values:
            records_lf = records_lf.filter(_condition_expr(column, values))
    return records_lf


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
    "/inspections/{inspection_time}/{wafer_key}/defect-ids.bin",
    responses={
        200: {
            "description": "Return sorted defect ids as little-endian Int32 bytes",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def get_inspection_defect_ids_binary(
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
        count=max(inspection.defects, 0),
    )
    try:
        defect_ids = await sorted_defect_ids_from_lazyframe(samples_lf)
    except ScPlotPointsRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=encode_defect_ids_int32le(defect_ids),
        media_type="application/octet-stream",
    )


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
    filters: ScFilterParams = Depends(get_sc_filter_params),
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
    samples_lf = _apply_sample_filters(
        samples_lf,
        class_number=filters.class_numbers,
        rough_bin=filters.rough_bins,
        predicted_label=filters.predictions,
        label=filters.annotations,
        test_id=filters.test_ids,
        adder=filters.adders,
        cluster_id=filters.cluster_ids,
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
        group_by=filters.legend_group_by,
    )
    return Response(content=body, media_type="application/x-protobuf")


@router.get(
    "/datasets/{dataset_id}/defect-ids.bin",
    responses={
        200: {
            "description": "Return sorted dataset defect ids as little-endian Int32 bytes",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def get_sc_dataset_defect_ids_binary(
    dataset_id: str,
    service: ScPlotPointsServiceDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    try:
        body = await service.build_defect_ids_response(dataset_id, org.id)
    except ScPlotPointsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScPlotPointsRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=body, media_type="application/octet-stream")


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
    filters: ScFilterParams = Depends(get_sc_filter_params),
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
            legend_group_by=filters.legend_group_by,
            class_numbers=filters.class_numbers,
            rough_bins=filters.rough_bins,
            predictions=filters.predictions,
            annotations=filters.annotations,
            test_ids=filters.test_ids,
            adders=filters.adders,
            cluster_ids=filters.cluster_ids,
        )
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


def _sample_table_cache_path(
    *,
    inspection_time: datetime,
    wafer_key: int,
    reticle_size_x: int,
    reticle_size_y: int,
    reticle_offset_x: int,
    reticle_offset_y: int,
) -> Path:
    payload = {
        "inspection_time": inspection_time.isoformat(),
        "wafer_key": wafer_key,
        "reticle_size_x": reticle_size_x,
        "reticle_size_y": reticle_size_y,
        "reticle_offset_x": reticle_offset_x,
        "reticle_offset_y": reticle_offset_y,
        "version": 1,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return _SAMPLE_TABLE_CACHE_DIR / f"{digest}.parquet"


async def _load_or_build_sample_table_df(
    *,
    upstream_reader: Any,
    inspection_time: datetime,
    wafer_key: int,
    row_count: int,
    reticle_size_x: int,
    reticle_size_y: int,
    reticle_offset_x: int,
    reticle_offset_y: int,
) -> pl.DataFrame:
    cache_path = _sample_table_cache_path(
        inspection_time=inspection_time,
        wafer_key=wafer_key,
        reticle_size_x=reticle_size_x,
        reticle_size_y=reticle_size_y,
        reticle_offset_x=reticle_offset_x,
        reticle_offset_y=reticle_offset_y,
    )
    if cache_path.exists():
        return pl.read_parquet(cache_path)

    samples_lf = await upstream_reader.list_samples(
        inspection_time,
        wafer_key,
        offset=0,
        count=row_count,
        reticle_size_x=reticle_size_x,
        reticle_size_y=reticle_size_y,
        reticle_offset_x=reticle_offset_x,
        reticle_offset_y=reticle_offset_y,
    )
    samples_df = await samples_lf.collect_async()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(f".{__import__('uuid').uuid4().hex}.tmp")
    samples_df.write_parquet(tmp_path)
    tmp_path.replace(cache_path)
    return samples_df


def _apply_sample_table_filter(
    samples_df: pl.DataFrame,
    filter_params: dict[str, Any] | None,
) -> pl.DataFrame:
    if not filter_params:
        return samples_df
    for field, filter_value in filter_params.items():
        col = _SAMPLE_TABLE_COLUMNS.get(field)
        if col is None or col not in samples_df.columns:
            continue
        if filter_value.operator == "in":
            values = [
                str(value) if field == "defect_id" else value
                for value in filter_value.values
            ]
            samples_df = samples_df.filter(
                pl.col(col).cast(pl.Utf8).is_in(values)
                if field == "defect_id"
                else pl.col(col).is_in(values)
            )
        else:
            samples_df = samples_df.filter(
                (pl.col(col) >= filter_value.min) & (pl.col(col) <= filter_value.max)
            )
    return samples_df


def _apply_sample_table_sort(
    samples_df: pl.DataFrame,
    sort_params: Any | None,
    requested: list[str] | None,
) -> pl.DataFrame:
    if sort_params:
        sort_field = _SAMPLE_TABLE_COLUMNS.get(sort_params.field)
        if sort_field is not None and sort_field in samples_df.columns:
            return samples_df.sort(
                sort_field, descending=(sort_params.direction == "desc")
            )
    if requested is not None:
        request_order = {defect_id: index for index, defect_id in enumerate(requested)}
        return (
            samples_df.with_columns(
                pl.col("defect_id")
                .cast(pl.Utf8)
                .replace_strict(request_order, default=len(request_order))
                .alias("_request_order")
            )
            .sort("_request_order")
            .drop("_request_order")
        )
    return (
        samples_df.sort("defect_id")
        if "defect_id" in samples_df.columns
        else samples_df
    )


def _sample_table_row_from_dict(row: dict[str, Any]) -> ScSampleTableRow:
    return ScSampleTableRow(
        defect_id=str(row["defect_id"]),
        rough_bin=row["rough_bin"],
        class_number=row["class_number"],
        test_id=row["test_id"],
        wafer_x=row["wafer_x"],
        wafer_y=row["wafer_y"],
        index_x=row["index_x"],
        index_y=row["index_y"],
        adder=row["adder"],
        cluster_id=row["cluster"],
        die_x=row["index_x"],
        die_y=row["index_y"],
        reticle_x=row.get("reticle_x", 0),
        reticle_y=row.get("reticle_y", 0),
        size_x=row["size_x"],
        size_y=row["size_y"],
        size_d=row["size_d"],
        area=row["area"],
        final_bin=row["final_bin"],
        manual_bin=row["manual_bin"],
        kill_ratio=row["kill_ratio"],
    )


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
    anchor = (
        int(payload.anchor) if payload.anchor and payload.anchor.isdigit() else None
    )
    limit = payload.limit if payload.anchor is not None else payload.page_size
    offset = anchor if anchor is not None else payload.page * payload.page_size
    filter_params = payload.filter
    sort_params = payload.sort
    reticle_size_x = payload.reticle_x_die_count
    reticle_size_y = payload.reticle_y_die_count
    reticle_offset_x = payload.reticle_x_die_shift
    reticle_offset_y = payload.reticle_y_die_shift

    requested = list(dict.fromkeys(defect_ids)) if defect_ids else None
    requested_set = set(requested) if requested else None

    row_count = (
        max(inspection.defects, len(requested), 100_000)
        if requested is not None
        else inspection.defects
    )
    samples_df = await _load_or_build_sample_table_df(
        upstream_reader=upstream_reader,
        inspection_time=insp_dt,
        wafer_key=wafer_key,
        row_count=row_count,
        reticle_size_x=reticle_size_x,
        reticle_size_y=reticle_size_y,
        reticle_offset_x=reticle_offset_x,
        reticle_offset_y=reticle_offset_y,
    )

    if requested_set is not None:
        samples_df = samples_df.filter(
            pl.col("defect_id").cast(pl.Utf8).is_in(requested_set)
        )

    samples_df = _apply_sample_table_filter(samples_df, filter_params)
    samples_df = _apply_sample_table_sort(samples_df, sort_params, requested)

    total_matched = len(samples_df)
    page_df = samples_df.slice(offset, limit)
    matched = [_sample_table_row_from_dict(row) for row in page_df.to_dicts()]
    next_offset = offset + len(matched)
    next_anchor = str(next_offset) if next_offset < total_matched else None

    return ScSampleTableRowsResponse(
        items=matched,
        total=total_matched,
        next_anchor=next_anchor,
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


# ── SC annotation endpoints under datasets namespace ──────────────────────
# These routes semantically belong to SC but sit under /datasets/
# because they operate on dataset-owned SC samples. Using a separate
# sub-router avoids the /api/v1/sc/ prefix while keeping the code in
# the SC module that owns the domain logic.

sc_datasets_router = APIRouter(prefix="/api/v1", tags=["sc"])


@sc_datasets_router.post(
    "/datasets/{dataset_id}/annotations/bulk-sc",
    response_model=ScBulkAnnotationResponse,
)
async def sc_bulk_create_annotations(
    dataset_id: str,
    payload: ScBulkAnnotationRequest,
    dataset_reader: ScDatasetReaderDep,
    dataset_store: ScDatasetStoreDep,
    dataset_service: DatasetServiceDep,
    repo: Annotated[DatasetRepository, Depends(get_repository)],
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> ScBulkAnnotationResponse:
    ds = await dataset_reader.get_dataset(dataset_id, org_id=org.id)
    if ds is None:
        ds = await dataset_reader.get_dataset(dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")

    defect_ids = {item.defect_id for item in payload.annotations}
    mapping = await dataset_store.map_defect_ids_to_sample_ids(
        dataset_reader, dataset_id, defect_ids, org_id=org.id
    )

    created = 0
    created_labels: set[str] = set()
    for item in payload.annotations:
        sample_id = mapping.get(item.defect_id)
        if sample_id is None:
            continue
        ann = Annotation(
            id=__import__("uuid").uuid4().hex,
            sample_id=sample_id,
            label=item.label,
            created_by=current_user.id,
        )
        await dataset_reader.create_annotation(ann, dataset_id=dataset_id)
        created += 1
        created_labels.add(item.label)

    if created_labels:
        await dataset_service.merge_label_space(dataset_id, created_labels)

    return ScBulkAnnotationResponse(created=created)


@router.get(
    "/datasets/{dataset_id}/samples/{sample_id}/images/{image_id}",
    response_class=Response,
)
async def serve_sc_sample_image(
    dataset_id: str,
    sample_id: str,
    image_id: str,
    org: Annotated[Organization, Depends(get_current_org)],
    current_user: Annotated[User, Depends(get_current_user)],
    image_fetcher: ScImageFetcherDep,
    payload_store: DatasetPayloadStoreDep,
) -> Response:
    from typing import cast as _cast
    from platform_runtime.sparse.reader import SparseManifestReader
    from app.shared.domain.protocols import ArtifactStorage

    store = payload_store
    storage: ArtifactStorage = store._storage  # type: ignore[reportPrivateUsage]
    reader = SparseManifestReader()

    try:
        manifest = await payload_store.get_manifest(dataset_id, org.id)
    except (FileNotFoundError, KeyError):
        raise HTTPException(
            status_code=404,
            detail=f"Dataset not found or has no manifest: {dataset_id}",
        )

    locator = manifest.sample_index.get(sample_id)
    if locator is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sample not found in dataset {dataset_id}: {sample_id}",
        )

    if locator.shard_index < 0 or locator.shard_index >= len(manifest.shards):
        raise HTTPException(
            status_code=404,
            detail=f"Shard index out of range for sample {sample_id}",
        )

    shard = manifest.shards[locator.shard_index]
    if locator.row_index < 0 or locator.row_index >= shard.row_count:
        raise HTTPException(
            status_code=404,
            detail=f"Row index out of range for sample {sample_id}",
        )

    try:
        rows = await reader.read_row_batch(
            shard.uri,
            locator.row_index,
            1,
            storage,
            columns=["images", "inspection_time", "wafer_key", "defect_id"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read shard row: {exc}",
        )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Sample row not found in shard: {sample_id}",
        )

    row = rows[0]
    images_raw = row.get("images")
    if images_raw is None:
        raise HTTPException(
            status_code=404,
            detail=f"No images column for sample: {sample_id}",
        )

    images_list: list[dict[str, object]] = []
    if isinstance(images_raw, list):
        images_list = [dict(img) if isinstance(img, dict) else {} for img in images_raw]

    matched: dict[str, object] | None = None
    for img in images_list:
        if str(img.get("image_id", "")) == image_id:
            matched = img
            break

    if matched is None:
        raise HTTPException(
            status_code=404,
            detail=f"Image {image_id} not found in sample {sample_id}",
        )

    raw_bytes = matched.get("bytes")
    if isinstance(raw_bytes, bytes):
        content_type = str(matched.get("content_type", ""))
        if not content_type or "/" not in content_type:
            content_type = "application/octet-stream"
        filename = str(matched.get("filename", f"{sample_id}_{image_id}"))
        return Response(
            content=raw_bytes,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=1200",
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )

    inspection_time = str(row.get("inspection_time", ""))
    wafer_key_raw = row.get("wafer_key", 0)
    wafer_key = int(_cast(int, wafer_key_raw)) if wafer_key_raw is not None else 0
    defect_id = str(row.get("defect_id", ""))
    image_type = str(matched.get("image_type", ""))
    review_image_id_raw = matched.get("review_image_id")
    review_image_id = (
        int(_cast(int, review_image_id_raw))
        if review_image_id_raw is not None
        else None
    )

    fetched_bytes = await image_fetcher.get_image_bytes(
        inspection_time=inspection_time,
        wafer_key=wafer_key,
        defect_id=defect_id,
        image_type=image_type,
        review_image_id=review_image_id,
    )

    content_type = str(matched.get("content_type", ""))
    if not content_type or "/" not in content_type:
        content_type = "application/octet-stream"
    filename = str(matched.get("filename", f"{sample_id}_{image_id}"))

    return Response(
        content=fetched_bytes,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=1200",
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )
