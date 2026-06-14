from __future__ import annotations

from typing import cast

from grpc import aio as grpc_aio

from proto_stubs.imageparser.v1 import service_pb2 as pb
from proto_stubs.imageparser.v1 import service_pb2_grpc as pb_grpc


class GrpcImageFetcher:
    def __init__(self, addr: str = "image-parser:9092") -> None:
        self._addr = addr
        self._channel: grpc_aio.Channel | None = None
        self._stub: pb_grpc.ImageParserStub | None = None

    def _ensure_channel(self) -> pb_grpc.ImageParserStub:
        if self._stub is None:
            self._channel = grpc_aio.insecure_channel(self._addr)
            self._stub = pb_grpc.ImageParserStub(self._channel)
        return self._stub

    async def get_image_bytes(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
        s3_path: str | None = None,
        review_image_id: int | None = None,
    ) -> bytes:
        stub = self._ensure_channel()
        req = pb.GetScImageRequest(
            inspection_time=inspection_time,
            wafer_key=wafer_key,
            defect_id=defect_id,
            image_type=image_type,
            review_image_id=review_image_id or 0,
        )
        resp = await stub.GetScImage(req)
        return resp.image_data

    async def get_image_bytes_batch(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        images: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        stub = self._ensure_channel()
        refs = [
            pb.ScImageRef(
                defect_id=str(img.get("defect_id", "")),
                image_type=str(img.get("image_type", "")),
                review_image_id=int(cast(object, img.get("review_image_id", 0)) or 0),  # type: ignore[arg-type]
            )
            for img in images
        ]
        req = pb.BatchGetScImageRequest(
            inspection_time=inspection_time,
            wafer_key=wafer_key,
            images=refs,
        )
        resp = await stub.BatchGetScImage(req)
        return [
            {
                "defect_id": r.defect_id,
                "image_type": r.image_type,
                "image_data": r.image_data,
                "content_type": r.content_type,
                "error": r.error,
            }
            for r in resp.results
        ]

    async def warm_cache(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        defect_ids: list[int] | None = None,
    ) -> dict[str, object]:
        stub = self._ensure_channel()
        req = pb.WarmScCacheRequest(
            inspection_time=inspection_time,
            wafer_key=wafer_key,
            defect_ids=defect_ids or [],
        )
        resp = await stub.WarmScCache(req)
        return {"status": resp.status, "zips_warmed": resp.zips_warmed}

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None
