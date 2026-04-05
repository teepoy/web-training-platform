from __future__ import annotations

import io
import logging
from concurrent import futures

import grpc
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from embedding_pb.embedding_pb2 import (
    EmbedBatchResponse,
    EmbedResponse,
    HealthResponse,
)
from embedding_pb.embedding_pb2_grpc import (
    EmbeddingServiceServicer,
    add_EmbeddingServiceServicer_to_server,
)

logger = logging.getLogger(__name__)


class CLIPEmbeddingServicer(EmbeddingServiceServicer):

    def __init__(self, default_model: str = "openai/clip-vit-base-patch32"):
        self._default_model = default_model
        self._models: dict[str, CLIPModel] = {}
        self._processors: dict[str, CLIPProcessor] = {}

    def _load(self, model_name: str) -> tuple[CLIPModel, CLIPProcessor]:
        if model_name not in self._models:
            logger.info("Loading model %s", model_name)
            processor = CLIPProcessor.from_pretrained(model_name)
            model = CLIPModel.from_pretrained(model_name)
            model.eval()
            self._processors[model_name] = processor
            self._models[model_name] = model
        return self._models[model_name], self._processors[model_name]

    def _embed_one(self, image_bytes: bytes, model_name: str) -> list[float]:
        model, processor = self._load(model_name)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        inputs = processor(images=image, return_tensors="pt")
        with torch.no_grad():
            features = model.get_image_features(**inputs)
            features = features / features.norm(dim=-1, keepdim=True)
        return features[0].tolist()

    def Embed(self, request, context):
        model_name = request.model_name or self._default_model
        try:
            vec = self._embed_one(request.image_data, model_name)
        except Exception as exc:
            context.abort(grpc.StatusCode.INTERNAL, str(exc))
            return EmbedResponse()
        return EmbedResponse(
            embedding=vec,
            model_name=model_name,
            dimension=len(vec),
        )

    def EmbedBatch(self, request, context):
        model_name = request.model_name or self._default_model
        results = []
        for img_bytes in request.images:
            try:
                vec = self._embed_one(img_bytes, model_name)
                results.append(EmbedResponse(
                    embedding=vec,
                    model_name=model_name,
                    dimension=len(vec),
                ))
            except Exception as exc:
                context.abort(grpc.StatusCode.INTERNAL, str(exc))
                return EmbedBatchResponse()
        return EmbedBatchResponse(embeddings=results)

    def Health(self, request, context):
        return HealthResponse(healthy=True, model_name=self._default_model)


def serve(port: int = 50051, max_workers: int = 4):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    add_EmbeddingServiceServicer_to_server(CLIPEmbeddingServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    logger.info("Embedding gRPC server listening on port %d", port)
    server.start()
    server.wait_for_termination()
