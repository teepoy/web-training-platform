from __future__ import annotations

from datetime import UTC, datetime

from prefect import flow, get_run_logger, task

from app.container import Container
from app.domain.models import PredictionEvent, Sample
from app.domain.types import JobStatus


@task(name="predict-chunk")
async def predict_chunk(
    model_id: str,
    org_id: str,
    target: str,
    prompt: str | None,
    sample_ids: list[str],
) -> list[dict]:
    container = Container()
    svc = container.prediction_service()
    model = await container.repository().get_model(model_id, org_id)
    if model is None:
        raise ValueError(f"Model not found: {model_id}")
    samples: list[Sample] = []
    for sample_id in sample_ids:
        sample = await container.repository().get_sample(sample_id)
        if sample is not None:
            samples.append(sample)
    if not samples:
        return []
    dataset = await container.repository().get_dataset(samples[0].dataset_id, org_id)
    if dataset is None:
        raise ValueError(f"Dataset not found: {samples[0].dataset_id}")
    return await svc._predict_via_worker(
        model=model,
        samples=samples,
        label_space=list(dataset.task_spec.label_space),
        target=target,
        prompt=prompt,
    )


@task(name="embed-chunk")
async def embed_chunk(
    dataset_id: str,
    org_id: str,
    embed_model: str,
    force: bool,
    sample_ids: list[str],
) -> dict:
    container = Container()
    repo = container.repository()
    svc = container.feature_ops()
    samples: list[Sample] = []
    for sample_id in sample_ids:
        sample = await repo.get_sample(sample_id)
        if sample is not None and sample.dataset_id == dataset_id:
            samples.append(sample)
    if not samples:
        return {"count": 0, "computed": 0, "skipped": 0, "embedding_model": embed_model, "status": "completed"}
    return await svc.extract_features_via_worker(
        samples=samples,
        embed_model=embed_model,
        force=force,
        storage=container.artifact_storage(),
    )


@task(name="persist-chunk")
async def persist_chunk_results(
    job_id: str,
    model_id: str,
    org_id: str,
    target: str,
    model_version: str | None,
    sample_ids: list[str],
    worker_results: list[dict],
) -> dict:
    container = Container()
    svc = container.prediction_service()
    repo = container.repository()
    model = await repo.get_model(model_id, org_id)
    if model is None:
        raise ValueError(f"Model not found: {model_id}")
    version_tag = model_version or f"model-{model_id[:8]}"
    ls_client = svc._get_ls_client()
    worker_by_sample = {str(item.get("sample_id", "")): item for item in worker_results}
    successful = 0
    failed = 0
    predictions: list[dict] = []
    for sample_id in sample_ids:
        sample = await repo.get_sample(sample_id)
        if sample is None:
            failed += 1
            continue
        result = await svc._prediction_result_from_worker(
            sample=sample,
            worker_result=worker_by_sample.get(sample.id, {"sample_id": sample.id, "error": "missing worker result"}),
            model_version=version_tag,
            ls_client=ls_client,
            target=target,
        )
        predictions.append(result.model_dump(mode="json"))
        if result.error:
            failed += 1
        else:
            successful += 1
    await repo.add_prediction_event(
        PredictionEvent(
            job_id=job_id,
            ts=datetime.now(UTC),
            message="prediction chunk persisted",
            payload={"successful": successful, "failed": failed, "processed": len(sample_ids)},
        )
    )
    return {
        "predictions": predictions,
        "successful": successful,
        "failed": failed,
        "processed": len(sample_ids),
    }


async def run_prediction_job(
    job_id: str,
    dataset_id: str,
    model_id: str,
    org_id: str,
    target: str,
    model_version: str | None,
    sample_ids: list[str] | None,
    prompt: str | None = None,
) -> dict:
    container = Container()
    repo = container.repository()
    dataset = await repo.get_dataset(dataset_id, org_id)
    if dataset is None:
        raise ValueError(f"Dataset not found: {dataset_id}")

    if sample_ids:
        selected_ids = [sid for sid in sample_ids if await repo.get_sample(sid) is not None]
    else:
        selected_ids: list[str] = []
        offset = 0
        page_size = 100
        while True:
            batch, total = await repo.list_samples(dataset_id, offset=offset, limit=page_size)
            selected_ids.extend(sample.id for sample in batch)
            offset += page_size
            if offset >= total:
                break

    summary: dict = {
        "model_id": model_id,
        "dataset_id": dataset_id,
        "total_samples": len(selected_ids),
        "successful": 0,
        "failed": 0,
        "predictions": [],
        "processed": 0,
        "started_at": datetime.now(UTC).isoformat(),
        "model_version": model_version or f"model-{model_id[:8]}",
    }
    await repo.update_prediction_job_status(job_id, JobStatus.RUNNING, summary=summary)
    await repo.add_prediction_event(
        PredictionEvent(job_id=job_id, ts=datetime.now(UTC), message="prediction flow running", payload={"total_samples": len(selected_ids)})
    )

    chunk_size = 32
    for start in range(0, len(selected_ids), chunk_size):
        current_job = await repo.get_prediction_job(job_id, org_id=org_id)
        if current_job is not None and str(current_job.status) in {"cancelled", "JobStatus.CANCELLED"}:
            summary["completed_at"] = datetime.now(UTC).isoformat()
            summary["cancelled"] = True
            await repo.update_prediction_job_status(job_id, JobStatus.CANCELLED, summary=summary)
            await repo.add_prediction_event(
                PredictionEvent(job_id=job_id, ts=datetime.now(UTC), message="prediction flow cancelled", payload={"summary": summary})
            )
            return summary
        chunk_ids = selected_ids[start:start + chunk_size]
        if target == "embedding":
            embed_model = prompt or "openai/clip-vit-base-patch32"
            force = bool(model_version == "force")
            chunk_summary = await embed_chunk(
                dataset_id=dataset_id,
                org_id=org_id,
                embed_model=embed_model,
                force=force,
                sample_ids=chunk_ids,
            )
            summary["successful"] += int(chunk_summary.get("computed", 0))
            summary["failed"] += int(chunk_summary.get("skipped", 0))
            summary["processed"] += int(chunk_summary.get("count", 0))
            summary["embedding_model"] = chunk_summary.get("embedding_model", embed_model)
        else:
            worker_results = await predict_chunk(
                model_id=model_id,
                org_id=org_id,
                target=target,
                prompt=prompt,
                sample_ids=chunk_ids,
            )
            chunk_summary = await persist_chunk_results(
                job_id=job_id,
                model_id=model_id,
                org_id=org_id,
                target=target,
                model_version=model_version,
                sample_ids=chunk_ids,
                worker_results=worker_results,
            )
            summary["successful"] += int(chunk_summary.get("successful", 0))
            summary["failed"] += int(chunk_summary.get("failed", 0))
            summary["processed"] += int(chunk_summary.get("processed", 0))
            summary["predictions"].extend(chunk_summary.get("predictions", []))
        await repo.update_prediction_job_status(job_id, JobStatus.RUNNING, summary=summary)

    summary["completed_at"] = datetime.now(UTC).isoformat()
    await repo.update_prediction_job_status(job_id, JobStatus.COMPLETED, summary=summary)
    await repo.add_prediction_event(
        PredictionEvent(job_id=job_id, ts=datetime.now(UTC), message="prediction flow completed", payload={"summary": summary})
    )
    return summary


@flow(name="predict-job")
async def predict_job(
    job_id: str,
    dataset_id: str,
    model_id: str,
    org_id: str,
    created_by: str = "system",
    target: str = "image_classification",
    model_version: str | None = None,
    sample_ids: list[str] | None = None,
    prompt: str | None = None,
) -> dict:
    logger = get_run_logger()
    logger.info(
        "Starting predict-job: job_id=%s dataset_id=%s model_id=%s org_id=%s target=%s created_by=%s",
        job_id,
        dataset_id,
        model_id,
        org_id,
        target,
        created_by,
    )
    result = await run_prediction_job(
        job_id=job_id,
        dataset_id=dataset_id,
        model_id=model_id,
        org_id=org_id,
        target=target,
        model_version=model_version,
        sample_ids=sample_ids,
        prompt=prompt,
    )
    logger.info(
        "Prediction complete: total=%s successful=%s failed=%s",
        result.get("total_samples"),
        result.get("successful"),
        result.get("failed"),
    )
    return result
