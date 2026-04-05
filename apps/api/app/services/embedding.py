from __future__ import annotations

import asyncio
import logging

import grpc

from embedding_pb.embedding_pb2 import EmbedBatchRequest, EmbedRequest, HealthRequest
from embedding_pb.embedding_pb2_grpc import EmbeddingServiceStub

logger = logging.getLogger(__name__)


class EmbeddingClient:

    def __init__(self, grpc_target: str = "localhost:50051"):
        self._target = grpc_target
        self._channel: grpc.Channel | None = None
        self._stub: EmbeddingServiceStub | None = None

    def _ensure_channel(self) -> EmbeddingServiceStub:
        if self._stub is None:
            self._channel = grpc.insecure_channel(self._target)
            self._stub = EmbeddingServiceStub(self._channel)
        return self._stub

    def _embed_sync(self, image_bytes: bytes, model_name: str) -> list[float]:
        stub = self._ensure_channel()
        response = stub.Embed(EmbedRequest(image_data=image_bytes, model_name=model_name))
        return list(response.embedding)

    async def embed_image(
        self,
        image_bytes: bytes,
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> list[float]:
        return await asyncio.to_thread(self._embed_sync, image_bytes, model_name)

    def _embed_batch_sync(self, image_bytes_list: list[bytes], model_name: str) -> list[list[float]]:
        stub = self._ensure_channel()
        response = stub.EmbedBatch(
            EmbedBatchRequest(images=image_bytes_list, model_name=model_name),
        )
        return [list(r.embedding) for r in response.embeddings]

    async def embed_batch(
        self,
        image_bytes_list: list[bytes],
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> list[list[float]]:
        return await asyncio.to_thread(self._embed_batch_sync, image_bytes_list, model_name)

    async def health(self) -> bool:
        def _check() -> bool:
            try:
                stub = self._ensure_channel()
                resp = stub.Health(HealthRequest())
                return resp.healthy
            except grpc.RpcError:
                return False
        return await asyncio.to_thread(_check)

    def close(self):
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None
