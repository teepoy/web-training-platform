from __future__ import annotations

import grpc

from datetime import datetime

from proto_stubs.sc.v1 import upstream_pb2 as pb
from proto_stubs.sc.v1 import upstream_pb2_grpc as pb_grpc

from .cache import QueryCache
from .upstream_db import InspectionZipsDB, UpstreamDB


class ScUpstreamService(pb_grpc.ScUpstreamServicer):
    def __init__(
        self, upstream_db: UpstreamDB, zips_db: InspectionZipsDB, cache: QueryCache
    ) -> None:
        self._db = upstream_db
        self._zips = zips_db
        self._cache = cache

    def Health(
        self, request: pb.HealthRequest, context: grpc.ServicerContext
    ) -> pb.HealthResponse:
        return pb.HealthResponse(status="ok")

    async def GetInspection(
        self, request: pb.GetInspectionRequest, context: grpc.ServicerContext
    ) -> pb.GetInspectionResponse:
        try:
            dt = datetime.fromisoformat(request.inspection_time)
        except ValueError:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "invalid inspection_time format"
            )
            return pb.GetInspectionResponse()

        it = request.inspection_time
        wk = request.wafer_key
        cached = await self._cache.get_inspection(it, wk)
        if cached is not None:
            return _to_inspection_response(cached)

        record = await self._db.get_inspection(dt, wk)
        if record is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "inspection not found")
            return pb.GetInspectionResponse()

        await self._cache.set_inspection(it, wk, record)
        return _to_inspection_response(record)

    async def ListInspections(
        self, request: pb.ListInspectionsRequest, context: grpc.ServicerContext
    ) -> pb.ListInspectionsResponse:
        try:
            start = datetime.fromisoformat(request.start_time)
            end = datetime.fromisoformat(request.end_time)
        except ValueError:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid time format")
            return pb.ListInspectionsResponse()

        cached = await self._cache.get_list_inspections(
            request.start_time, request.end_time
        )
        if cached is not None:
            items = [_to_summary_item(r) for r in cached]
            return pb.ListInspectionsResponse(items=items)

        lf = await self._db.list_inspections(start, end)
        rows = lf.collect().to_dicts()
        await self._cache.set_list_inspections(
            request.start_time, request.end_time, rows
        )
        items = [_to_summary_item(r) for r in rows]
        return pb.ListInspectionsResponse(items=items)

    async def GetInspectionPatchZips(
        self, request: pb.GetInspectionPatchZipsRequest, context: grpc.ServicerContext
    ) -> pb.GetInspectionPatchZipsResponse:
        try:
            dt = datetime.fromisoformat(request.inspection_time)
        except ValueError:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "invalid inspection_time format"
            )
            return pb.GetInspectionPatchZipsResponse()

        it = request.inspection_time
        lot = request.lot_id
        wafer = request.wafer_id
        dev = request.device
        layer = request.layer_id

        cached = await self._cache.get_patch_zips(it, lot, wafer, dev, layer)
        if cached is not None:
            return pb.GetInspectionPatchZipsResponse(
                zips=[
                    pb.ZipRef(s3_bucket=z["s3_bucket"], s3_key=z["s3_key"])
                    for z in cached
                ]
            )

        zips = await self._zips.get_inspection_patch_zips(dt, lot, wafer, dev, layer)
        await self._cache.set_patch_zips(it, lot, wafer, dev, layer, zips)
        return pb.GetInspectionPatchZipsResponse(
            zips=[pb.ZipRef(s3_bucket=z["s3_bucket"], s3_key=z["s3_key"]) for z in zips]
        )

    async def GetReviewImageFileSpec(
        self, request: pb.GetReviewImageFileSpecRequest, context: grpc.ServicerContext
    ) -> pb.GetReviewImageFileSpecResponse:
        try:
            dt = datetime.fromisoformat(request.inspection_time)
        except ValueError:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "invalid inspection_time format"
            )
            return pb.GetReviewImageFileSpecResponse()

        images = await self._cache.get_list_review_images(
            request.inspection_time, request.wafer_key
        )
        if images is not None:
            for img in images:
                if (
                    img["defect_id"] == request.defect_id
                    and img["image_id"] == request.image_id
                ):
                    return pb.GetReviewImageFileSpecResponse(
                        image_filespec=img["image_filespec"]
                    )
            context.abort(grpc.StatusCode.NOT_FOUND, "review image not found")
            return pb.GetReviewImageFileSpecResponse()

        it = request.inspection_time
        wk = request.wafer_key
        images = await self._db.list_review_images(dt, wk)
        await self._cache.set_list_review_images(it, wk, images)
        for img in images:
            if (
                img["defect_id"] == request.defect_id
                and img["image_id"] == request.image_id
            ):
                return pb.GetReviewImageFileSpecResponse(
                    image_filespec=img["image_filespec"]
                )
        context.abort(grpc.StatusCode.NOT_FOUND, "review image not found")
        return pb.GetReviewImageFileSpecResponse()

    async def ListReviewImages(
        self, request: pb.ListReviewImagesRequest, context: grpc.ServicerContext
    ) -> pb.ListReviewImagesResponse:
        try:
            dt = datetime.fromisoformat(request.inspection_time)
        except ValueError:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "invalid inspection_time format"
            )
            return pb.ListReviewImagesResponse()

        it = request.inspection_time
        wk = request.wafer_key
        images = await self._cache.get_list_review_images(it, wk)
        if images is None:
            images = await self._db.list_review_images(dt, wk)
            await self._cache.set_list_review_images(it, wk, images)

        defect_id = request.defect_id if request.defect_id else 0
        refs = [
            pb.ReviewImageRef(
                image_filespec=img["image_filespec"],
                defect_id=img["defect_id"],
                image_id=img["image_id"],
                image_type=img["image_type"],
            )
            for img in images
            if defect_id == 0 or img["defect_id"] == defect_id
        ]
        return pb.ListReviewImagesResponse(images=refs)


def _to_inspection_response(record: dict) -> pb.GetInspectionResponse:
    return pb.GetInspectionResponse(
        inspection_time=record.get("inspection_time", ""),
        wafer_key=record.get("wafer_key", 0),
        lot_id=record.get("lot_id", ""),
        wafer_id=record.get("wafer_id", ""),
        device=record.get("device", ""),
        layer_id=record.get("layer_id", ""),
        center_x=record.get("center_x", 0),
        center_y=record.get("center_y", 0),
        origin_x=record.get("origin_x", 0),
        origin_y=record.get("origin_y", 0),
        die_size_x=record.get("die_size_x", 0),
        die_size_y=record.get("die_size_y", 0),
        eqp_id=record.get("eqp_id", ""),
        recipe_id=record.get("recipe_id", ""),
        defects=record.get("defects", 0),
        images=record.get("images", 0),
        origin_index_x=record.get("origin_index_x", 0),
        origin_index_y=record.get("origin_index_y", 0),
        latest_update=record.get("latest_update", 0),
    )


def _to_summary_item(record: dict) -> pb.InspectionSummary:
    return pb.InspectionSummary(
        inspection_time=str(record.get("inspection_time", "")),
        wafer_key=record.get("wafer_key", 0),
        lot_id=record.get("lot_id", ""),
        wafer_id=record.get("wafer_id", ""),
        device=record.get("device", ""),
        layer_id=record.get("layer_id", ""),
        eqp_id=record.get("inspect_equip_id", ""),
        recipe_id=str(record.get("recipe_id", "")),
        defects=record.get("defects", 0),
        images=record.get("images", 0),
        center_x=record.get("center_x", 0),
        center_y=record.get("center_y", 0),
        origin_x=record.get("origin_x", 0),
        origin_y=record.get("origin_y", 0),
        die_size_x=record.get("die_size_x", 0),
        die_size_y=record.get("die_size_y", 0),
        origin_index_x=record.get("origin_index_x", 0),
        origin_index_y=record.get("origin_index_y", 0),
    )
