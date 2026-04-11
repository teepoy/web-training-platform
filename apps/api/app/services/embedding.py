from __future__ import annotations

import asyncio
import logging

import grpc

from embedding_pb.embedding_pb2 import (
    ClassifyBatchRequest,
    ClassifyRequest,
    EmbedBatchRequest,
    EmbedRequest,
    HealthRequest,
)
from embedding_pb.embedding_pb2_grpc import EmbeddingServiceStub

logger = logging.getLogger(__name__)


class EmbeddingClient:

    def __init__(self, grpc_target: str = "localhost:50051", timeout_seconds: float = 5.0):
        self._target = grpc_target
        self._timeout_seconds = timeout_seconds
        self._channel: grpc.Channel | None = None
        self._stub: EmbeddingServiceStub | None = None

    def _ensure_channel(self) -> EmbeddingServiceStub:
        if self._stub is None:
            self._channel = grpc.insecure_channel(self._target)
            self._stub = EmbeddingServiceStub(self._channel)
        return self._stub

    def _embed_sync(self, image_bytes: bytes, model_name: str) -> list[float]:
        stub = self._ensure_channel()
        response = stub.Embed(
            EmbedRequest(image_data=image_bytes, model_name=model_name),
            timeout=self._timeout_seconds,
        )
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
            timeout=self._timeout_seconds,
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
                resp = stub.Health(HealthRequest(), timeout=self._timeout_seconds)
                return resp.healthy
            except grpc.RpcError:
                return False
        return await asyncio.to_thread(_check)

    def close(self):
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None

    # Classification methods

    def _classify_sync(
        self,
        image_bytes: bytes,
        labels: list[str],
        model_name: str,
    ) -> tuple[str, float, dict[str, float]]:
        """Synchronous classification call.
        
        Returns (predicted_label, confidence, {label: score}).
        """
        stub = self._ensure_channel()
        response = stub.Classify(
            ClassifyRequest(
                image_data=image_bytes,
                labels=labels,
                model_name=model_name,
            ),
            timeout=self._timeout_seconds,
        )
        scores = {s.label: s.score for s in response.scores}
        return response.predicted_label, response.confidence, scores

    async def classify_image(
        self,
        image_bytes: bytes,
        labels: list[str],
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> tuple[str, float, dict[str, float]]:
        """Zero-shot CLIP classification for a single image.
        
        Parameters
        ----------
        image_bytes:
            Raw image bytes (JPEG, PNG, etc.)
        labels:
            List of class labels for classification.
        model_name:
            CLIP model to use (default: openai/clip-vit-base-patch32).
            
        Returns
        -------
        tuple[str, float, dict[str, float]]
            (predicted_label, confidence, {label: score})
        """
        return await asyncio.to_thread(
            self._classify_sync, image_bytes, labels, model_name
        )

    def _classify_batch_sync(
        self,
        image_bytes_list: list[bytes],
        labels: list[str],
        model_name: str,
    ) -> list[tuple[str, float, dict[str, float]]]:
        """Synchronous batch classification call."""
        stub = self._ensure_channel()
        response = stub.ClassifyBatch(
            ClassifyBatchRequest(
                images=image_bytes_list,
                labels=labels,
                model_name=model_name,
            ),
            timeout=self._timeout_seconds,
        )
        results = []
        for pred in response.predictions:
            scores = {s.label: s.score for s in pred.scores}
            results.append((pred.predicted_label, pred.confidence, scores))
        return results

    async def classify_batch(
        self,
        image_bytes_list: list[bytes],
        labels: list[str],
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> list[tuple[str, float, dict[str, float]]]:
        """Zero-shot CLIP classification for multiple images.
        
        Parameters
        ----------
        image_bytes_list:
            List of raw image bytes.
        labels:
            List of class labels for classification.
        model_name:
            CLIP model to use.
            
        Returns
        -------
        list[tuple[str, float, dict[str, float]]]
            List of (predicted_label, confidence, {label: score}) tuples.
        """
        return await asyncio.to_thread(
            self._classify_batch_sync, image_bytes_list, labels, model_name
        )
