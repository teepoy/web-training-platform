from __future__ import annotations

import base64
import io
import json
import math
import os
import subprocess
import threading
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.job_registry import JobRegistry, JobConflictError
from app.train_handler import run_training_background, cancel_training
from app.metrics import (
    get_metrics,
    jobs_active as _m_jobs_active,
    jobs_total as _m_jobs_total,
    job_duration_seconds as _m_job_duration,
    prediction_batch_duration_seconds as _m_predict_duration,
    embedding_batch_duration_seconds as _m_embed_duration,
    TASK_KIND_TRAINING,
    TASK_KIND_PREDICTION,
    TASK_KIND_EMBEDDING,
)

# ── GPU detection (best-effort, graceful degradation) ──────────────


def _detect_gpu_info() -> dict[str, object]:
    gpu_info: dict[str, object] = {"available": False, "reason": "CUDA not available"}

    try:
        import torch
    except ImportError:
        return gpu_info

    try:
        cuda_available = torch.cuda.is_available()
    except Exception:
        return gpu_info

    if not cuda_available:
        return gpu_info

    try:
        subprocess.run(["nvidia-smi", "-L"], check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return gpu_info

    device_count = torch.cuda.device_count()
    device_name = torch.cuda.get_device_name(0) if device_count > 0 else "unknown"
    return {
        "available": True,
        "device_count": device_count,
        "device_name": device_name,
    }




# ── Job registry (V1 in-memory, lost on restart) ───────────────────

_job_registry = JobRegistry()

# ── Stub helpers (shared with existing predict / embed) ────────────


def _image_embedding_from_bytes(image_bytes: bytes, dim: int = 64) -> list[float]:
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as img:
        gray = img.convert("L").resize((8, 8))
        pixels = list(gray.tobytes())
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
    if not api_key:
        raise ValueError("LLM api_key is not configured")
    if not model:
        raise ValueError("LLM model is not configured")

    import litellm

    litellm.suppress_debug_info = True

    data_uri = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        },
    ]

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "timeout": 30.0,
        "api_key": api_key,
    }
    if base_url:
        kwargs["api_base"] = base_url

    try:
        response = await litellm.acompletion(**kwargs)
    except Exception as exc:
        raise ValueError(f"LLM request failed: {exc}") from exc

    choices = response.choices  # type: ignore[union-attr]
    if not choices:
        raise ValueError("LLM response has no choices")
    content = choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response content is empty")
    return content.strip()


# ── Request / Response models ──────────────────────────────────────

# -- Predict (existing, unchanged) --


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


# -- Embed (existing, unchanged) --


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


# -- Train (new) --


class TrainRequest(BaseModel):
    platform_job_id: str
    preset_id: str
    dataset_id: str
    model_id: str = ""
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    artifact_prefix: str = ""


class TrainSubmitResponse(BaseModel):
    job_id: str
    status: str
    position: int = 0


class TrainResubmitResponse(BaseModel):
    job_id: str
    status: str
    detail: str


class TrainStatusResponse(BaseModel):
    job_id: str
    platform_job_id: str
    status: str
    progress: float
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    updated_at: str | None = None


class TrainCancelResponse(BaseModel):
    job_id: str
    status: str


class TrainLogsResponse(BaseModel):
    job_id: str
    logs: list[dict[str, Any]] = Field(default_factory=list)


# ── App ────────────────────────────────────────────────────────────

app = FastAPI(title="Finetune GPU Worker", version="0.1.0")


# ── Health ─────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "gpu-worker",
        "capabilities": ["train", "predict", "embed"],
        "gpu_info": _detect_gpu_info(),
        "ready_for_training": not _job_registry.has_active_training(),
    }


# ── Metrics ────────────────────────────────────────────────────────


@app.get("/metrics")
def metrics() -> Any:
    from fastapi.responses import Response

    return Response(content=get_metrics(), media_type="text/plain; charset=utf-8")


# ── Train ──────────────────────────────────────────────────────────


@app.post(
    "/v1/train",
    response_model=TrainSubmitResponse | TrainResubmitResponse,
    status_code=202,
)
def train_submit(payload: TrainRequest) -> Any:
    from fastapi.responses import JSONResponse

    try:
        record, is_duplicate = _job_registry.submit(payload.platform_job_id)
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    if is_duplicate:
        return JSONResponse(
            status_code=409,
            content={
                "job_id": record.gpu_job_id,
                "status": "already_submitted",
                "detail": "Job with this platform_job_id already exists",
            },
        )

    _m_jobs_active.labels(task_kind=TASK_KIND_TRAINING).set(1)
    _m_jobs_total.labels(task_kind=TASK_KIND_TRAINING, status="pending").inc()

    t = threading.Thread(
        target=run_training_background,
        args=(
            _job_registry,
            record.gpu_job_id,
            payload.platform_job_id,
            payload.dataset_id,
            payload.preset_id,
        ),
        daemon=True,
    )
    t.start()

    return TrainSubmitResponse(
        job_id=record.gpu_job_id,
        status="accepted",
        position=0,
    )


@app.get("/v1/train/{job_id}", response_model=TrainStatusResponse)
def train_status(job_id: str) -> TrainStatusResponse:
    record = _job_registry.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")
    d = record.to_dict()
    return TrainStatusResponse(**d)


@app.post("/v1/train/{job_id}/cancel", response_model=TrainCancelResponse)
def train_cancel(job_id: str) -> TrainCancelResponse:
    try:
        record = _job_registry.cancel(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    cancel_training(job_id)

    _m_jobs_active.labels(task_kind=TASK_KIND_TRAINING).set(0)
    _m_jobs_total.labels(task_kind=TASK_KIND_TRAINING, status="cancelled").inc()

    return TrainCancelResponse(job_id=record.gpu_job_id, status="cancelled")


@app.get("/v1/train/{job_id}/logs", response_model=TrainLogsResponse)
def train_logs(job_id: str, tail: int = 100) -> TrainLogsResponse:
    try:
        logs = _job_registry.get_logs(job_id, tail=tail)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")
    return TrainLogsResponse(job_id=job_id, logs=logs)


# ── Predict ────────────────────────────────────────────────────────


@app.post("/v1/predict", response_model=PredictResponse)
async def predict(payload: PredictRequest) -> PredictResponse:
    t0 = time.monotonic()
    model_bytes = base64.b64decode(payload.model.content_b64)
    metadata = (
        payload.model.metadata if isinstance(payload.model.metadata, dict) else {}
    )
    predictions: list[PredictResponseItem] = []

    if payload.target == "vqa":
        for sample in payload.samples:
            question = sample.question.strip()
            if not sample.image_bytes_b64:
                predictions.append(
                    PredictResponseItem(
                        sample_id=sample.sample_id, error="missing image bytes"
                    )
                )
                continue
            if not question:
                predictions.append(
                    PredictResponseItem(
                        sample_id=sample.sample_id, error="missing question"
                    )
                )
                continue
            try:
                image_bytes = base64.b64decode(sample.image_bytes_b64)
                answer = await _answer_vqa(
                    image_bytes,
                    question,
                    str(
                        metadata.get(
                            "system_prompt",
                            "You are a helpful visual question answering assistant. Answer briefly and accurately based on the image.",
                        )
                    ),
                )
                predictions.append(
                    PredictResponseItem(
                        sample_id=sample.sample_id, label=answer, confidence=None
                    )
                )
            except Exception as exc:
                predictions.append(
                    PredictResponseItem(sample_id=sample.sample_id, error=str(exc))
                )
        _m_predict_duration.observe(time.monotonic() - t0)
        return PredictResponse(predictions=predictions)

    try:
        model_payload = json.loads(model_bytes.decode("utf-8"))
    except Exception:
        model_payload = {}

    prototypes = (
        model_payload.get("label_prototypes")
        if isinstance(model_payload, dict)
        else None
    )
    if not isinstance(prototypes, dict):
        prototypes = {}
    if not prototypes:
        label_space = payload.label_space or [
            str(x) for x in metadata.get("label_space", []) if str(x)
        ]
        for idx, label in enumerate(label_space):
            vec = [0.0] * 64
            vec[idx % 64] = 1.0
            prototypes[str(label)] = vec

    for sample in payload.samples:
        if not sample.image_bytes_b64:
            predictions.append(
                PredictResponseItem(
                    sample_id=sample.sample_id, error="missing image bytes"
                )
            )
            continue
        image_bytes = base64.b64decode(sample.image_bytes_b64)
        embedding = _image_embedding_from_bytes(image_bytes)
        if payload.target == "embedding":
            predictions.append(
                PredictResponseItem(
                    sample_id=sample.sample_id, label="embedding", confidence=1.0
                )
            )
            continue
        scores: dict[str, float] = {}
        for label, proto in prototypes.items():
            if isinstance(proto, list) and proto:
                scores[str(label)] = _cosine(embedding, [float(x) for x in proto])
        if not scores:
            predictions.append(
                PredictResponseItem(
                    sample_id=sample.sample_id, error="model has no label prototypes"
                )
            )
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

    _m_predict_duration.observe(time.monotonic() - t0)
    return PredictResponse(predictions=predictions)


# ── Embed ──────────────────────────────────────────────────────────


@app.post("/v1/embed", response_model=EmbedResponse)
def embed(payload: EmbedRequest) -> EmbedResponse:
    t0 = time.monotonic()
    embeddings: list[EmbedResponseItem] = []
    for sample in payload.samples:
        if not sample.image_bytes_b64:
            embeddings.append(
                EmbedResponseItem(
                    sample_id=sample.sample_id, error="missing image bytes"
                )
            )
            continue
        image_bytes = base64.b64decode(sample.image_bytes_b64)
        embeddings.append(
            EmbedResponseItem(
                sample_id=sample.sample_id,
                embedding=_image_embedding_from_bytes(image_bytes),
            )
        )
    _m_embed_duration.observe(time.monotonic() - t0)
    return EmbedResponse(embeddings=embeddings)
