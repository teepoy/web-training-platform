from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

import polars as pl

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.modules.auth.port.http.deps import get_current_org, get_current_user
from app.modules.datasets.port.http.deps import (
    DatasetServiceDep,
    get_dataset_storage_factory,
)
from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.sc.port.http.deps import (
    DatasetPayloadStoreDep,
    ScDatasetReaderDep,
    ScDatasetStoreDep,
    ScImageFetcherDep,
    ScImportServiceDep,
    ScPlotPointsServiceDep,
    ScUpstreamReaderDep,
)
from app.modules.sc.app.services.sc_plot_points_service import (
    ScPlotPointsNotFoundError,
    ScPlotPointsRejectedError,
    _apply_sample_filters,
    apply_sample_table_filter,
    encode_defect_ids_int32le,
    filter_box_defect_ids,
    sorted_defect_ids_from_lazyframe,
)
from app.modules.sc.domain.upstream_reader import ScSampleProgressCallback
from app.modules.sc.domain.entities.sc_import import ScImportStatus
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
    ScReclassifySampleTableRow,
    ScReclassifySampleTableRowsResponse,
    ScReviewImageItem,
    ScReviewImagesByDefectItem,
    ScSampleTableRow,
    ScSampleTableRowsRequest,
    ScSampleTableRowsResponse,
)
from app.shared.api.schemas import Annotation, Organization, User
from app.shared.sse.emit import emit_sse
from app.shared.sse.events import (
    DoneEvent,
    ScDataEvent,
    ScErrorEvent,
    ScProgressEvent,
    SSEEvent,
)

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

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
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
    sample_filter: Annotated[str | None, Query()] = None,
) -> ScFilterParams:
    parsed_sample_filter = None
    if sample_filter:
        try:
            parsed = json.loads(sample_filter)
            parsed_sample_filter = ScSampleTableRowsRequest.model_validate(
                {"filter": parsed}
            ).filter
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid sample_filter: {exc}",
            ) from exc
    return ScFilterParams(
        class_numbers=class_numbers,
        rough_bins=rough_bins,
        predictions=predictions,
        annotations=annotations,
        test_ids=test_ids,
        adders=adders,
        cluster_ids=cluster_ids,
        legend_group_by=legend_group_by,
        sample_filter=parsed_sample_filter,
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
    records_df = await records_lf.collect_async()
    eqp_values = _parse_top_level_condition(eqp_id)
    if (
        eqp_values
        and not records_df.is_empty()
        and "inspect_equip_id" in records_df.columns
    ):
        records_df = records_df.filter(_condition_expr("inspect_equip_id", eqp_values))

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
            return datetime(
                dt.year,
                dt.month,
                dt.day,
                dt.hour,
                dt.minute,
                dt.second,
                dt.microsecond,
                tzinfo=timezone.utc,
            )
        return dt.astimezone(timezone.utc)
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
    insp_dt, inspection = await _resolve_inspection_or_404(
        upstream_reader, inspection_time, wafer_key
    )
    body = await _build_inspection_map_points_payload(
        upstream_reader=upstream_reader,
        inspection=inspection,
        insp_dt=insp_dt,
        wafer_key=wafer_key,
        reticle_x_die_count=reticle_x_die_count,
        reticle_y_die_count=reticle_y_die_count,
        reticle_x_die_shift=reticle_x_die_shift,
        reticle_y_die_shift=reticle_y_die_shift,
        sampled=sampled,
        grid_size_nm=grid_size_nm,
        zoom_x=zoom_x,
        zoom_y=zoom_y,
        zoom_w=zoom_w,
        zoom_h=zoom_h,
        mode=mode,
        filters=filters,
    )
    return Response(content=body, media_type="application/x-protobuf")


async def _build_inspection_map_points_payload(
    *,
    upstream_reader: Any,
    inspection: Any,
    insp_dt: datetime,
    wafer_key: int,
    reticle_x_die_count: int,
    reticle_y_die_count: int,
    reticle_x_die_shift: int,
    reticle_y_die_shift: int,
    sampled: bool,
    grid_size_nm: int,
    zoom_x: int | None,
    zoom_y: int | None,
    zoom_w: int | None,
    zoom_h: int | None,
    mode: Literal["wafer", "die", "reticle"] | None,
    filters: ScFilterParams,
    on_sample_progress: ScSampleProgressCallback | None = None,
) -> bytes:
    samples_lf = await upstream_reader.list_samples(
        insp_dt,
        wafer_key,
        offset=0,
        count=1_000_000,
        reticle_size_x=reticle_x_die_count,
        reticle_size_y=reticle_y_die_count,
        reticle_offset_x=reticle_x_die_shift,
        reticle_offset_y=reticle_y_die_shift,
        on_progress=on_sample_progress,
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
    samples_lf = apply_sample_table_filter(samples_lf, filters.sample_filter)
    df = await samples_lf.collect_async()
    df = df.with_columns((pl.col("images") > 0).cast(pl.Int32).alias("has_review"))
    return make_wafer_map_response_pb(
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


@router.get("/inspections/{inspection_time}/{wafer_key}/map-points/stream")
async def stream_inspection_map_points_progress(
    request: Request,
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
) -> StreamingResponse:
    insp_dt, inspection = await _resolve_inspection_or_404(
        upstream_reader, inspection_time, wafer_key
    )

    async def event_generator():
        if await request.is_disconnected():
            return
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="sc.map-points",
                    status="loading",
                    message="Preparing map points",
                    total_count=inspection.defects,
                )
            )
        )
        progress_queue: asyncio.Queue[int] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _on_sample_progress(loaded: int) -> None:
            loop.call_soon_threadsafe(progress_queue.put_nowait, loaded)

        build_task = asyncio.create_task(
            _build_inspection_map_points_payload(
                upstream_reader=upstream_reader,
                inspection=inspection,
                insp_dt=insp_dt,
                wafer_key=wafer_key,
                reticle_x_die_count=reticle_x_die_count,
                reticle_y_die_count=reticle_y_die_count,
                reticle_x_die_shift=reticle_x_die_shift,
                reticle_y_die_shift=reticle_y_die_shift,
                sampled=sampled,
                grid_size_nm=grid_size_nm,
                zoom_x=zoom_x,
                zoom_y=zoom_y,
                zoom_w=zoom_w,
                zoom_h=zoom_h,
                mode=mode,
                filters=filters,
                on_sample_progress=_on_sample_progress,
            )
        )
        last_loaded = 0
        try:
            while not build_task.done():
                if await request.is_disconnected():
                    build_task.cancel()
                    return
                try:
                    loaded = await asyncio.wait_for(progress_queue.get(), timeout=0.25)
                except TimeoutError:
                    continue
                loaded = min(max(loaded, 0), max(inspection.defects, 0))
                if loaded <= last_loaded:
                    continue
                last_loaded = loaded
                yield emit_sse(
                    SSEEvent(
                        ScProgressEvent(
                            event_type="progress",
                            operation="sc.map-points",
                            status="loading",
                            message="Preparing map points",
                            loaded_count=loaded,
                            total_count=inspection.defects,
                        )
                    )
                )
            await build_task
            while not progress_queue.empty():
                loaded = progress_queue.get_nowait()
                loaded = min(max(loaded, 0), max(inspection.defects, 0))
                if loaded <= last_loaded:
                    continue
                last_loaded = loaded
                yield emit_sse(
                    SSEEvent(
                        ScProgressEvent(
                            event_type="progress",
                            operation="sc.map-points",
                            status="loading",
                            message="Preparing map points",
                            loaded_count=loaded,
                            total_count=inspection.defects,
                        )
                    )
                )
        except Exception as exc:
            if not build_task.done():
                build_task.cancel()
            yield emit_sse(
                SSEEvent(
                    ScErrorEvent(
                        event_type="error",
                        status="failed",
                        error=str(exc),
                    )
                )
            )
            return
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="sc.map-points",
                    status="cached",
                    message="Map points are ready",
                    loaded_count=inspection.defects,
                    total_count=inspection.defects,
                )
            )
        )
        yield emit_sse(SSEEvent(DoneEvent(event_type="done", rows=inspection.defects)))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


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
    samples_lf = apply_sample_table_filter(samples_lf, payload.filter)
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
) -> StreamingResponse:
    async def stream_body():
        yield await service.build_plot_points_response(
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
            filter_params=filters.sample_filter,
        )

    try:
        await service.ensure_plot_points_allowed(dataset_id, org.id)
    except ScPlotPointsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScPlotPointsRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(stream_body(), media_type="application/x-protobuf")


@router.get("/datasets/{dataset_id}/plot-points/stream")
async def stream_sc_dataset_plot_points_progress(
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
) -> StreamingResponse:
    try:
        await service.ensure_plot_points_allowed(dataset_id, org.id)
    except ScPlotPointsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScPlotPointsRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_generator():
        if await request.is_disconnected():
            return
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="sc.plot-points",
                    status="loading",
                    dataset_id=dataset_id,
                    message="Preparing plot points",
                )
            )
        )
        try:
            payload = await service.build_plot_points_response(
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
                filter_params=filters.sample_filter,
            )
        except Exception as exc:
            yield emit_sse(
                SSEEvent(
                    ScErrorEvent(
                        event_type="error",
                        status="failed",
                        error=str(exc),
                    )
                )
            )
            return
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="sc.plot-points",
                    status="ready",
                    dataset_id=dataset_id,
                    message="Plot points are ready",
                    loaded_count=len(payload),
                )
            )
        )
        yield emit_sse(SSEEvent(DoneEvent(event_type="done")))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


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
            filter_params=payload.filter,
        )
    except ScPlotPointsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScPlotPointsRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScBoxFilterResponse(defect_ids=defect_ids, total=len(defect_ids))


@router.post(
    "/datasets/{dataset_id}/sample-table-rows",
    response_model=ScReclassifySampleTableRowsResponse,
)
async def get_sc_dataset_sample_table_rows(
    dataset_id: str,
    payload: ScSampleTableRowsRequest,
    service: ScPlotPointsServiceDep,
    upstream_reader: ScUpstreamReaderDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ScReclassifySampleTableRowsResponse:
    try:
        rows, total, next_anchor = await service.build_dataset_sample_table_rows(
            dataset_id,
            org.id,
            upstream_reader=upstream_reader,
            defect_ids=payload.defect_ids,
            anchor=payload.anchor,
            page=payload.page,
            page_size=payload.page_size,
            limit=payload.limit,
            filter_params=payload.filter,
            sort_params=payload.sort,
            reticle_x_die_count=payload.reticle_x_die_count,
            reticle_y_die_count=payload.reticle_y_die_count,
            reticle_x_die_shift=payload.reticle_x_die_shift,
            reticle_y_die_shift=payload.reticle_y_die_shift,
        )
    except ScPlotPointsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScPlotPointsRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScReclassifySampleTableRowsResponse(
        items=[ScReclassifySampleTableRow.model_validate(row) for row in rows],
        total=total,
        next_anchor=next_anchor,
    )


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
        if filter_value.operator in {"in", "not_in"}:
            values = [
                str(value) if field == "defect_id" else value
                for value in filter_value.values
            ]
            predicate = (
                pl.col(col).cast(pl.Utf8).is_in(values)
                if field == "defect_id"
                else pl.col(col).is_in(values)
            )
            samples_df = samples_df.filter(
                predicate if filter_value.operator == "in" else ~predicate
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
    def int_or_zero(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, float) and math.isnan(value):
            return 0
        return int(value)

    return ScSampleTableRow(
        defect_id=str(row["defect_id"]),
        rough_bin=int_or_zero(row["rough_bin"]),
        class_number=int_or_zero(row["class_number"]),
        test_id=int_or_zero(row["test_id"]),
        wafer_x=int_or_zero(row["wafer_x"]),
        wafer_y=int_or_zero(row["wafer_y"]),
        index_x=int_or_zero(row["index_x"]),
        index_y=int_or_zero(row["index_y"]),
        adder=int_or_zero(row["adder"]),
        cluster_id=None if row["cluster"] is None else int_or_zero(row["cluster"]),
        die_x=int_or_zero(row["index_x"]),
        die_y=int_or_zero(row["index_y"]),
        reticle_x=int_or_zero(row.get("reticle_x", 0)),
        reticle_y=int_or_zero(row.get("reticle_y", 0)),
        size_x=int_or_zero(row["size_x"]),
        size_y=int_or_zero(row["size_y"]),
        size_d=int_or_zero(row["size_d"]),
        area=int_or_zero(row["area"]),
        final_bin=int_or_zero(row["final_bin"]),
        manual_bin=int_or_zero(row["manual_bin"]),
        kill_ratio=row["kill_ratio"],
    )


async def _build_sample_table_rows_response(
    *,
    payload: ScSampleTableRowsRequest,
    upstream_reader: Any,
    insp_dt: datetime,
    inspection: Any,
    wafer_key: int,
) -> ScSampleTableRowsResponse:
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


async def _resolve_inspection_or_404(
    upstream_reader: Any,
    inspection_time: str,
    wafer_key: int,
) -> tuple[datetime, Any]:
    insp_dt = _parse_inspection_time(inspection_time)
    inspection = await upstream_reader.get_inspection(insp_dt, wafer_key)
    if inspection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Inspection not found: {inspection_time}/{wafer_key}",
        )
    return insp_dt, inspection


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
    insp_dt, inspection = await _resolve_inspection_or_404(
        upstream_reader, inspection_time, wafer_key
    )
    return await _build_sample_table_rows_response(
        payload=payload,
        upstream_reader=upstream_reader,
        insp_dt=insp_dt,
        inspection=inspection,
        wafer_key=wafer_key,
    )


@router.post("/inspections/{inspection_time}/{wafer_key}/sample-table-rows/stream")
async def stream_inspection_sample_table_rows(
    payload: ScSampleTableRowsRequest,
    request: Request,
    upstream_reader: ScUpstreamReaderDep,
    inspection_time: str,
    wafer_key: int,
) -> StreamingResponse:
    insp_dt, inspection = await _resolve_inspection_or_404(
        upstream_reader, inspection_time, wafer_key
    )

    async def event_generator():
        if await request.is_disconnected():
            return
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="sc.sample-table",
                    status="loading",
                    message="Loading sample rows",
                    total_count=inspection.defects,
                )
            )
        )
        try:
            response = await _build_sample_table_rows_response(
                payload=payload,
                upstream_reader=upstream_reader,
                insp_dt=insp_dt,
                inspection=inspection,
                wafer_key=wafer_key,
            )
        except Exception as exc:
            yield emit_sse(
                SSEEvent(
                    ScErrorEvent(
                        event_type="error",
                        status="failed",
                        error=str(exc),
                    )
                )
            )
            return
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="sc.sample-table",
                    status="serializing",
                    message="Serializing sample rows",
                    loaded_count=len(response.items),
                    total_count=response.total,
                )
            )
        )
        yield emit_sse(
            SSEEvent(
                ScDataEvent(
                    event_type="data",
                    operation="sc.sample-table",
                    payload=response.model_dump(mode="json"),
                )
            )
        )
        yield emit_sse(SSEEvent(DoneEvent(event_type="done")))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
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
    status = await sc_import_service.submit_import(
        source_inspection_time=payload.source_inspection_time,
        source_wafer_key=payload.source_wafer_key,
        dataset_name=payload.dataset_name,
        storage_mode=payload.storage_mode,
        org_id=org.id,
        created_by=current_user.id,
        filters=payload.filters,
        label_space=payload.label_space,
        max_rows=payload.max_rows,
    )
    if status.status == "failed":
        return JSONResponse(
            content=ScImportResponse(
                status="failed",
                error=status.error,
            ).model_dump(mode="json"),
            status_code=200,
        )
    return ScImportResponse(
        status=status.status,
        dataset_id=status.dataset_id,
        imported_count=status.imported_count,
        error=status.error,
    )


@router.post("/import/stream")
async def stream_sc_import(
    payload: ScImportRequest,
    request: Request,
    sc_import_service: ScImportServiceDep,
    current_user: CurrentUserDep,
    org: CurrentOrgDep,
) -> StreamingResponse:
    progress_queue: asyncio.Queue[ScImportStatus] = asyncio.Queue()

    async def on_progress(status: ScImportStatus) -> None:
        await progress_queue.put(status)

    async def event_generator():
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="sc.import",
                    status="running",
                    message="Starting import",
                    imported_count=0,
                )
            )
        )
        import_task = asyncio.create_task(
            sc_import_service.submit_import(
                source_inspection_time=payload.source_inspection_time,
                source_wafer_key=payload.source_wafer_key,
                dataset_name=payload.dataset_name,
                storage_mode=payload.storage_mode,
                org_id=org.id,
                created_by=current_user.id,
                filters=payload.filters,
                label_space=payload.label_space,
                max_rows=payload.max_rows,
                on_progress=on_progress,
            )
        )
        try:
            while not import_task.done():
                if await request.is_disconnected():
                    import_task.cancel()
                    return
                try:
                    status = await asyncio.wait_for(
                        progress_queue.get(),
                        timeout=0.25,
                    )
                except TimeoutError:
                    continue
                yield emit_sse(
                    SSEEvent(
                        ScProgressEvent(
                            event_type="progress",
                            operation="sc.import",
                            status=status.status,
                            dataset_id=status.dataset_id or None,
                            imported_count=status.imported_count,
                            total_count=status.imported_count + status.remaining_count,
                        )
                    )
                )
            status = await import_task
        except Exception as exc:
            if not import_task.done():
                import_task.cancel()
            yield emit_sse(
                SSEEvent(
                    ScErrorEvent(
                        event_type="error",
                        status="failed",
                        error=str(exc),
                    )
                )
            )
            return

        if status.status == "failed":
            yield emit_sse(
                SSEEvent(
                    ScErrorEvent(
                        event_type="error",
                        status="failed",
                        error=status.error or "Import failed",
                    )
                )
            )
            return

        yield emit_sse(
            SSEEvent(
                ScDataEvent(
                    event_type="data",
                    operation="sc.import",
                    payload=ScImportResponse(
                        status=status.status,
                        dataset_id=status.dataset_id,
                        imported_count=status.imported_count,
                        error=status.error,
                    ).model_dump(mode="json"),
                )
            )
        )
        yield emit_sse(
            SSEEvent(
                DoneEvent(
                    event_type="done",
                    dataset_id=status.dataset_id,
                    rows=status.imported_count,
                )
            )
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
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
    storage_factory: Annotated[
        DatasetStorageFactory, Depends(get_dataset_storage_factory)
    ],
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
    annotations_to_create: list[Annotation] = []
    annotation_ids_to_delete: list[str] = []
    storage = await storage_factory.open(dataset_id, org.id)
    for item in payload.annotations:
        sample_id = mapping.get(item.defect_id)
        if sample_id is None:
            continue
        existing = await storage.list_annotations(sample_id=sample_id)
        if existing:
            annotation_ids_to_delete.extend(ann.id for ann in existing if ann.id)
        if item.label == "0":
            continue
        annotations_to_create.append(
            Annotation(
                sample_id=sample_id,
                label=item.label,
                created_by=current_user.id,
            )
        )
        created_labels.add(item.label)

    if annotation_ids_to_delete:
        await storage.delete_annotations(annotation_ids_to_delete)
    if annotations_to_create:
        created = await storage.create_annotations(annotations_to_create)

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
