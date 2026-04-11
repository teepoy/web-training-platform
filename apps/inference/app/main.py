from __future__ import annotations

import base64
import io
import json
import math
import os
from typing import Any

from fastapi import FastAPI
import httpx
from pydantic import BaseModel, Field


def _image_embedding_from_bytes(image_bytes: bytes, dim: int = 64) -> list[float]:
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as img:
        gray = img.convert("L").resize((8, 8))
        pixels = list(gray.getdata())
    vals = [float(p) / 255.0 for p in pixels]
    if len(vals) < dim:
        vals.extend([0.0] * (dim - len(vals)))
    vec = vals[:dim]
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def _answer_vqa(image_bytes: bytes, question: str, system_prompt: str) -> str:
    base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")
    if not base_url:
        raise ValueError("LLM base_url is not configured")
    if not api_key:
        raise ValueError("LLM api_key is not configured")
    if not model:
        raise ValueError("LLM model is not configured")
    data_uri = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
    if resp.status_code >= 400:
        raise ValueError(f"LLM request failed ({resp.status_code}): {resp.text}")
    body = resp.json()
    choices = body.get("choices", [])
    if not choices:
        raise ValueError("LLM response has no choices")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response content is empty")
    return content.strip()


class PredictModelPayload(BaseModel):
    id: str
    uri: str
    format: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_b64: str


class PredictSamplePayload(BaseModel):
    sample_id: str
    image_bytes_b64: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    image_uris: list[str] = Field(default_factory=list)
    question: str = ""
    text: str | None = None


class PredictRequest(BaseModel):
    model: PredictModelPayload
    target: str
    label_space: list[str] = Field(default_factory=list)
    samples: list[PredictSamplePayload] = Field(default_factory=list)


class PredictResponseItem(BaseModel):
    sample_id: str
    label: str = ""
    confidence: float | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    error: str | None = None


class PredictResponse(BaseModel):
    predictions: list[PredictResponseItem] = Field(default_factory=list)


class EmbedSamplePayload(BaseModel):
    sample_id: str
    image_bytes_b64: str | None = None


class EmbedRequest(BaseModel):
    model_name: str
    samples: list[EmbedSamplePayload] = Field(default_factory=list)


class EmbedResponseItem(BaseModel):
    sample_id: str
    embedding: list[float] = Field(default_factory=list)
    error: str | None = None


class EmbedResponse(BaseModel):
    embeddings: list[EmbedResponseItem] = Field(default_factory=list)


app = FastAPI(title="Finetune Inference Worker", version="0.1.0")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "inference-worker",
        "capabilities": ["predict-single", "predict-batch", "embed-single", "embed-batch"],
        "cache": {"policy": "warm-default", "loaded_models": 0},
    }


@app.post("/v1/predict", response_model=PredictResponse)
async def predict(payload: PredictRequest) -> PredictResponse:
    model_bytes = base64.b64decode(payload.model.content_b64)
    metadata = payload.model.metadata if isinstance(payload.model.metadata, dict) else {}
    predictions: list[PredictResponseItem] = []

    if payload.target == "vqa":
        for sample in payload.samples:
            question = sample.question.strip()
            if not sample.image_bytes_b64:
                predictions.append(PredictResponseItem(sample_id=sample.sample_id, error="missing image bytes"))
                continue
            if not question:
                predictions.append(PredictResponseItem(sample_id=sample.sample_id, error="missing question"))
                continue
            try:
                image_bytes = base64.b64decode(sample.image_bytes_b64)
                answer = await _answer_vqa(
                    image_bytes,
                    question,
                    str(metadata.get("system_prompt", "You are a helpful visual question answering assistant. Answer briefly and accurately based on the image.")),
                )
                predictions.append(PredictResponseItem(sample_id=sample.sample_id, label=answer, confidence=None))
            except Exception as exc:
                predictions.append(PredictResponseItem(sample_id=sample.sample_id, error=str(exc)))
        return PredictResponse(predictions=predictions)

    try:
        model_payload = json.loads(model_bytes.decode("utf-8"))
    except Exception:
        model_payload = {}

    prototypes = model_payload.get("label_prototypes") if isinstance(model_payload, dict) else None
    if not isinstance(prototypes, dict):
        prototypes = {}
    if not prototypes:
        label_space = payload.label_space or [str(x) for x in metadata.get("label_space", []) if str(x)]
        for idx, label in enumerate(label_space):
            vec = [0.0] * 64
            vec[idx % 64] = 1.0
            prototypes[str(label)] = vec

    for sample in payload.samples:
        if not sample.image_bytes_b64:
            predictions.append(PredictResponseItem(sample_id=sample.sample_id, error="missing image bytes"))
            continue
        image_bytes = base64.b64decode(sample.image_bytes_b64)
        embedding = _image_embedding_from_bytes(image_bytes)
        if payload.target == "embedding":
            predictions.append(PredictResponseItem(sample_id=sample.sample_id, label="embedding", confidence=1.0))
            continue
        scores: dict[str, float] = {}
        for label, proto in prototypes.items():
            if isinstance(proto, list) and proto:
                scores[str(label)] = _cosine(embedding, [float(x) for x in proto])
        if not scores:
            predictions.append(PredictResponseItem(sample_id=sample.sample_id, error="model has no label prototypes"))
            continue
        best_label = max(scores.items(), key=lambda x: x[1])[0]
        total = sum(max(v, 0.0) for v in scores.values())
        confidence = max(scores[best_label], 0.0) / total if total > 0 else 0.0
        predictions.append(
            PredictResponseItem(
                sample_id=sample.sample_id,
                label=best_label,
                confidence=confidence,
                scores=scores,
            )
        )

    return PredictResponse(predictions=predictions)


@app.post("/v1/embed", response_model=EmbedResponse)
def embed(payload: EmbedRequest) -> EmbedResponse:
    embeddings: list[EmbedResponseItem] = []
    for sample in payload.samples:
        if not sample.image_bytes_b64:
            embeddings.append(EmbedResponseItem(sample_id=sample.sample_id, error="missing image bytes"))
            continue
        image_bytes = base64.b64decode(sample.image_bytes_b64)
        embeddings.append(
            EmbedResponseItem(
                sample_id=sample.sample_id,
                embedding=_image_embedding_from_bytes(image_bytes),
            )
        )
    return EmbedResponse(embeddings=embeddings)
