from __future__ import annotations

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

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None
