from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from app.api.schemas import (
    CreateAnnotationRequest,
    CreateDatasetRequest,
    CreatePredictionRequest,
    CreatePresetRequest,
    CreateSampleRequest,
    CreateTrainingJobRequest,
    EditPredictionRequest,
    PaginatedResponse,
    UpdateAnnotationRequest,
    UpdateEmbedConfigRequest,
    UpdateSampleImageResponse,
)
from app.container import Container
from app.db.session import init_db
from app.domain.models import Annotation, Dataset, PredictionEdit, PredictionResult, Sample, TrainingEvent, TrainingJob, TrainingPreset


@asynccontextmanager
async def lifespan(_: FastAPI):
    cfg = container.config()
    if bool(cfg.db.auto_create):
        await init_db(container.db_engine())
    yield


app = FastAPI(title="Online Finetune API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

container = Container()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/datasets", response_model=Dataset)
async def create_dataset(payload: CreateDatasetRequest) -> Dataset:
    dataset = Dataset(name=payload.name, task_spec=payload.task_spec)
    return await container.repository().create_dataset(dataset)


@app.get("/api/v1/datasets", response_model=list[Dataset])
async def list_datasets() -> list[Dataset]:
    return await container.repository().list_datasets()


@app.get("/api/v1/datasets/{dataset_id}", response_model=Dataset)
async def get_dataset(dataset_id: str) -> Dataset:
    dataset = await container.repository().get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@app.post("/api/v1/datasets/{dataset_id}/samples", response_model=Sample)
async def create_sample(dataset_id: str, payload: CreateSampleRequest) -> Sample:
    if await container.repository().get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    sample = Sample(dataset_id=dataset_id, image_uris=payload.image_uris, metadata=payload.metadata)
    return await container.repository().create_sample(sample)


@app.get("/api/v1/datasets/{dataset_id}/samples", response_model=PaginatedResponse[Sample])
async def list_samples(
    dataset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
) -> PaginatedResponse[Sample]:
    items, total = await container.repository().list_samples(dataset_id, offset=offset, limit=limit)
    return PaginatedResponse(items=items, total=total)


@app.get("/api/v1/samples/{sample_id}", response_model=Sample)
async def get_sample(sample_id: str) -> Sample:
    sample = await container.repository().get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    return sample


@app.post("/api/v1/samples/{sample_id}/embed")
async def embed_sample(sample_id: str) -> dict:
    sample = await container.repository().get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    if not sample.image_uris:
        raise HTTPException(status_code=400, detail="no image")

    uri = sample.image_uris[0]
    if uri.startswith("data:"):
        try:
            _, encoded = uri.split(",", 1)
            image_bytes = base64.b64decode(encoded)
        except Exception:
            raise HTTPException(status_code=400, detail="malformed data URI")
    elif uri.startswith("s3://") or uri.startswith("memory://"):
        try:
            image_bytes = await container.artifact_storage().get_bytes(uri)
        except (FileNotFoundError, KeyError):
            raise HTTPException(status_code=404, detail="image not found")
    else:
        raise HTTPException(status_code=400, detail="unsupported URI scheme")

    dataset = await container.repository().get_dataset(sample.dataset_id)
    embed_model: str = (dataset.embed_config or {}).get("model", "openai/clip-vit-base-patch32") if dataset else "openai/clip-vit-base-patch32"
    embedding_svc = container.embedding_service()
    embedding = await embedding_svc.embed_image(image_bytes, model_name=embed_model)
    feature = await container.repository().upsert_sample_feature(sample_id, embedding, embed_model)
    return {
        "sample_id": feature.sample_id,
        "embed_model": feature.embed_model,
        "embedding_dim": len(feature.embedding),
    }


@app.post("/api/v1/annotations", response_model=Annotation)
async def create_annotation(payload: CreateAnnotationRequest) -> Annotation:
    if await container.repository().get_sample(payload.sample_id) is None:
        raise HTTPException(status_code=404, detail="sample not found")
    ann = Annotation(sample_id=payload.sample_id, label=payload.label, created_by=payload.created_by)
    return await container.repository().create_annotation(ann)


@app.get("/api/v1/samples/{sample_id}/annotations", response_model=list[Annotation])
async def list_annotations_for_sample(sample_id: str) -> list[Annotation]:
    if await container.repository().get_sample(sample_id) is None:
        raise HTTPException(status_code=404, detail="sample not found")
    return await container.repository().list_annotations_for_sample(sample_id)


@app.patch("/api/v1/annotations/{annotation_id}", response_model=Annotation)
async def update_annotation(annotation_id: str, payload: UpdateAnnotationRequest) -> Annotation:
    result = await container.repository().update_annotation(annotation_id, payload.label)
    if result is None:
        raise HTTPException(status_code=404, detail="annotation not found")
    return result


@app.delete("/api/v1/annotations/{annotation_id}", status_code=204)
async def delete_annotation(annotation_id: str) -> Response:
    deleted = await container.repository().delete_annotation(annotation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="annotation not found")
    return Response(status_code=204)


@app.post("/api/v1/training-presets", response_model=TrainingPreset)
async def create_preset(payload: CreatePresetRequest) -> TrainingPreset:
    preset = TrainingPreset(
        name=payload.name,
        model_spec=payload.model_spec,
        omegaconf_yaml=payload.omegaconf_yaml,
        dataloader_ref=payload.dataloader_ref,
    )
    return await container.repository().create_preset(preset)


@app.get("/api/v1/training-presets", response_model=list[TrainingPreset])
async def list_presets() -> list[TrainingPreset]:
    return await container.repository().list_presets()


@app.get("/api/v1/training-presets/{preset_id}", response_model=TrainingPreset)
async def get_preset(preset_id: str) -> TrainingPreset:
    preset = await container.repository().get_preset(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset


@app.post("/api/v1/training-jobs", response_model=TrainingJob)
async def create_training_job(payload: CreateTrainingJobRequest) -> TrainingJob:
    if await container.repository().get_dataset(payload.dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    if await container.repository().get_preset(payload.preset_id) is None:
        raise HTTPException(status_code=404, detail="preset not found")
    job = TrainingJob(dataset_id=payload.dataset_id, preset_id=payload.preset_id, created_by=payload.created_by)
    return await container.orchestrator().start_job(job)


@app.get("/api/v1/training-jobs", response_model=list[TrainingJob])
async def list_jobs() -> list[TrainingJob]:
    return await container.repository().list_jobs()


@app.get("/api/v1/training-jobs/{job_id}", response_model=TrainingJob)
async def get_job(job_id: str) -> TrainingJob:
    job = await container.repository().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/api/v1/training-jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, bool]:
    ok = await container.orchestrator().cancel_job(job_id)
    return {"cancelled": ok}


@app.get("/api/v1/training-jobs/{job_id}/events")
async def get_job_events(job_id: str, request: Request):
    if await container.repository().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_stream():
        idx = 0
        while True:
            if await request.is_disconnected():
                break
            events = await container.repository().list_events(job_id)
            while idx < len(events):
                line = f"data: {json.dumps(events[idx].model_dump(mode='json'))}\n\n"
                yield line
                idx += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/v1/training-jobs/{job_id}/events/history", response_model=PaginatedResponse[TrainingEvent])
async def get_job_events_history(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1),
) -> PaginatedResponse[TrainingEvent]:
    if await container.repository().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    items, total = await container.repository().list_events_paginated(job_id, offset=offset, limit=limit)
    return PaginatedResponse(items=items, total=total)


@app.post("/api/v1/training-jobs/{job_id}/mark-left")
async def mark_user_left(job_id: str) -> dict[str, bool]:
    if await container.repository().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"marked": await container.repository().mark_user_left(job_id)}


@app.post("/api/v1/predictions", response_model=PredictionResult)
async def create_prediction(payload: CreatePredictionRequest) -> PredictionResult:
    if await container.repository().get_sample(payload.sample_id) is None:
        raise HTTPException(status_code=404, detail="sample not found")
    pred = PredictionResult(
        sample_id=payload.sample_id,
        predicted_label=payload.predicted_label,
        score=payload.score,
        model_artifact_id=payload.model_artifact_id,
    )
    return await container.repository().create_prediction(pred)


@app.get("/api/v1/predictions", response_model=list[PredictionResult])
async def list_predictions() -> list[PredictionResult]:
    return await container.repository().list_predictions()


@app.patch("/api/v1/predictions/{prediction_id}", response_model=PredictionEdit)
async def edit_prediction(prediction_id: str, payload: EditPredictionRequest) -> PredictionEdit:
    if await container.repository().get_prediction(prediction_id) is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    edit = PredictionEdit(result_id=prediction_id, corrected_label=payload.corrected_label, edited_by=payload.edited_by)
    return await container.repository().create_prediction_edit(edit)


@app.get("/api/v1/exports/{dataset_id}")
async def export_dataset(dataset_id: str) -> dict:
    dataset = await container.repository().get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    samples, _ = await container.repository().list_samples(dataset_id, limit=100_000)
    anns = await container.repository().list_annotations_for_dataset(dataset_id)
    return container.artifacts().build_dataset_export(
        dataset=dataset,
        samples=samples,
        annotations=anns,
    )


@app.post("/api/v1/exports/{dataset_id}/persist")
async def export_dataset_persist(dataset_id: str) -> dict:
    dataset = await container.repository().get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    samples, _ = await container.repository().list_samples(dataset_id, limit=100_000)
    anns = await container.repository().list_annotations_for_dataset(dataset_id)
    uri = await container.artifacts().persist_dataset_export(dataset=dataset, samples=samples, annotations=anns)
    return {"uri": uri}


@app.post("/api/v1/datasets/{dataset_id}/features/extract")
async def extract_features(dataset_id: str, force: bool = Query(default=False)) -> dict:
    dataset = await container.repository().get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")

    embed_model: str = (dataset.embed_config or {}).get("model", "openai/clip-vit-base-patch32")

    # Count total samples
    samples, total = await container.repository().list_samples(dataset_id, limit=100_000)

    # Determine which samples need embedding via direct check
    # (efficient: avoid loading full ORM objects where possible)
    to_embed: list[str] = []
    for s in samples:
        feature = await container.repository().get_sample_feature(s.id)
        if feature is None or feature.embed_model != embed_model or force:
            to_embed.append(s.id)

    async def _background_embed() -> None:
        storage = container.artifact_storage()
        embedding_svc = container.embedding_service()
        repo = container.repository()
        for sid in to_embed:
            sample = await repo.get_sample(sid)
            if sample is None or not sample.image_uris:
                continue
            uri = sample.image_uris[0]
            try:
                if uri.startswith("data:"):
                    _, encoded = uri.split(",", 1)
                    image_bytes = base64.b64decode(encoded)
                else:
                    image_bytes = await storage.get_bytes(uri)
                embedding = await embedding_svc.embed_image(image_bytes, model_name=embed_model)
                await repo.upsert_sample_feature(sid, embedding, embed_model)
            except Exception:
                pass  # Don't let one failure stop the batch

    asyncio.create_task(_background_embed())

    return {"status": "processing", "total_samples": total, "to_embed": len(to_embed)}


@app.get("/api/v1/datasets/{dataset_id}/similarity/{sample_id}")
async def similarity_search(dataset_id: str, sample_id: str, k: int = 5) -> dict:
    if await container.repository().get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    sample = await container.repository().get_sample(sample_id)
    if sample is None or sample.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="sample not found")
    return await container.feature_ops().similarity_search(sample_id, dataset_id=dataset_id, k=k)


@app.get("/api/v1/datasets/{dataset_id}/selection-metrics")
async def selection_metrics(dataset_id: str) -> dict:
    if await container.repository().get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    samples, _ = await container.repository().list_samples(dataset_id, limit=100_000)
    sample_ids = [s.id for s in samples]
    fs = container.feature_ops()
    return {
        "uniqueness": fs.uniqueness_scores(sample_ids),
        "representativeness": fs.representativeness_scores(sample_ids),
    }


@app.get("/api/v1/datasets/{dataset_id}/hints/uncovered")
async def uncovered_hints(dataset_id: str) -> dict:
    if await container.repository().get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return container.feature_ops().uncovered_cluster_hints(dataset_id)


@app.get("/api/v1/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: str) -> Response:
    artifact = await container.repository().get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        data = await container.artifact_storage().get_bytes(artifact.uri)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="artifact data not found")
    return Response(content=data, media_type="application/octet-stream")


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@app.post("/api/v1/samples/{sample_id}/upload", response_model=UpdateSampleImageResponse)
async def upload_sample_image(sample_id: str, file: UploadFile = File(...)) -> UpdateSampleImageResponse:
    sample = await container.repository().get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="file must be an image")
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 10 MB limit")
    key = f"samples/{sample_id}/{file.filename}"
    uri = await container.artifact_storage().put_bytes(key, data, file.content_type or "application/octet-stream")
    existing_uris = list(sample.image_uris or [])
    index = len(existing_uris)
    updated_uris = existing_uris + [uri]
    await container.repository().update_sample_image_uris(sample_id, updated_uris)
    return UpdateSampleImageResponse(uri=uri, sample_id=sample_id, index=index)


@app.get("/api/v1/images/resolve")
async def resolve_image(uri: str = Query(...)) -> Response:
    # Reject http/https for security
    if uri.startswith("http://") or uri.startswith("https://"):
        raise HTTPException(status_code=400, detail="http/https URIs are not allowed")
    # Handle data: URIs
    if uri.startswith("data:"):
        try:
            header, encoded = uri.split(",", 1)
            mime_part = header.split(";")[0][len("data:"):]
            data = base64.b64decode(encoded)
            return Response(content=data, media_type=mime_part or "application/octet-stream")
        except Exception:
            raise HTTPException(status_code=400, detail="malformed data URI")
    # Handle storage URIs (s3:// or memory://)
    if uri.startswith("s3://") or uri.startswith("memory://"):
        try:
            data = await container.artifact_storage().get_bytes(uri)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="image not found")
        # Attempt to infer content type from URI extension
        lower_uri = uri.lower()
        if lower_uri.endswith(".png"):
            media_type = "image/png"
        elif lower_uri.endswith(".gif"):
            media_type = "image/gif"
        elif lower_uri.endswith(".webp"):
            media_type = "image/webp"
        else:
            media_type = "image/jpeg"
        return Response(content=data, media_type=media_type)
    raise HTTPException(status_code=400, detail="unsupported URI scheme")


# ---------------------------------------------------------------------------
# Embed config endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/datasets/{dataset_id}/embed-config")
async def get_embed_config(dataset_id: str) -> dict:
    dataset = await container.repository().get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return dataset.embed_config or {}


@app.patch("/api/v1/datasets/{dataset_id}/embed-config")
async def update_embed_config(dataset_id: str, payload: UpdateEmbedConfigRequest) -> dict:
    dataset = await container.repository().get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    new_config = {"model": payload.model, "dimension": payload.dimension}
    await container.repository().update_dataset_embed_config(dataset_id, new_config)
    return new_config


# ---------------------------------------------------------------------------
# Auth scaffold – always returns dummy data; OAuth not yet wired
# ---------------------------------------------------------------------------

_DUMMY_USER: dict = {
    "id": "dummy",
    "name": "Local User",
    "email": "user@local.dev",
    "roles": ["admin"],
}


@app.get("/api/v1/auth/me")
def auth_me() -> dict:
    return _DUMMY_USER


@app.post("/api/v1/auth/callback")
def auth_callback() -> dict:
    return {"token": "dummy-token", "user": _DUMMY_USER}
