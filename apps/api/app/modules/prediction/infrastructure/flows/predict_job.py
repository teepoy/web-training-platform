from __future__ import annotations
# pyright: reportMissingImports=false

from datetime import UTC, datetime
from typing import Any

from prefect import flow, get_run_logger, task

from app.core.config import load_config
from app.modules.datasets.application.services.feature_ops import FeatureOpsService
from app.modules.prediction.application.services.prediction_service import (
    PredictionService,
)
from app.shared.api.schemas import PredictionEvent, Sample
from app.shared.api.schemas import JobStatus


_app_container_ref: Any = None


def _sync_app_container_overrides(container: Any) -> None:
    return None


async def _with_flow_container():
    if _app_container_ref is not None:
        _sync_app_container_overrides(_app_container_ref)
        return _app_container_ref, False

    from app.composition import build_flow_container

    cfg = load_config()
    return build_flow_container(cfg), True


def _prediction_service(container) -> PredictionService:
    return PredictionService(
        repository=container.prediction_repository,
        artifact_storage=container.artifact_storage,
        config=container.config,
        embedding_client=container.embedding_client,
        llm_client=container.llm_client,
        inference_worker=container.inference_worker,
        gpu_worker=container.gpu_worker,
    )


def _feature_ops_service(container) -> FeatureOpsService:
    return FeatureOpsService(
        repository=container.prediction_repository,
        embedding_service=container.embedding_client,
        inference_worker=container.inference_worker,
        gpu_worker=container.gpu_worker,
    )


@task(name="predict-chunk")
async def predict_chunk(
    job_id: str,
    model_id: str,
    org_id: str,
    target: str,
    prompt: str | None,
    sample_ids: list[str],
) -> list[dict]:
    container, should_close = await _with_flow_container()
    try:
        repo = container.prediction_repository
        svc = _prediction_service(container)
        model = await repo.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        samples: list[Sample] = []
        for sample_id in sample_ids:
            sample = await repo.get_sample(sample_id)
            if sample is not None:
                samples.append(sample)
        if not samples:
            return []
        dataset = await repo.get_dataset(samples[0].dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {samples[0].dataset_id}")
        results = await svc._predict_via_worker(
            model=model,
            samples=samples,
            label_space=list(dataset.task_spec.label_space),
            target=target,
            prompt=prompt,
        )
        await _persist_worker_results(
            repo=repo,
            svc=svc,
            job_id=job_id,
            model=model,
            org_id=org_id,
            target=target,
            model_version=f"model-{model.id[:8]}",
            sample_ids=sample_ids,
            worker_results=results,
        )
        return results
    finally:
        if should_close:
            await container.close()


@task(name="embed-chunk")
async def embed_chunk(
    dataset_id: str,
    org_id: str,
    embed_model: str,
    force: bool,
    sample_ids: list[str],
) -> dict:
    container, should_close = await _with_flow_container()
    try:
        repo = container.prediction_repository
        svc = _feature_ops_service(container)
        samples: list[Sample] = []
        for sample_id in sample_ids:
            sample = await repo.get_sample(sample_id)
            if sample is not None and sample.dataset_id == dataset_id:
                samples.append(sample)
        if not samples:
            return {
                "count": 0,
                "computed": 0,
                "skipped": 0,
                "embedding_model": embed_model,
                "status": "completed",
            }
        return await svc.extract_features_via_worker(
            samples=samples,
            embed_model=embed_model,
            force=force,
            storage=container.artifact_storage,
        )
    finally:
        if should_close:
            await container.close()


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
    container, should_close = await _with_flow_container()
    try:
        svc = _prediction_service(container)
        repo = container.prediction_repository
        model = await repo.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        return await _persist_worker_results(
            repo=repo,
            svc=svc,
            job_id=job_id,
            model=model,
            org_id=org_id,
            target=target,
            model_version=model_version,
            sample_ids=sample_ids,
            worker_results=worker_results,
        )
    finally:
        if should_close:
            await container.close()


async def _persist_worker_results(
    *,
    repo,
    svc: PredictionService,
    job_id: str,
    model,
    org_id: str,
    target: str,
    model_version: str | None,
    sample_ids: list[str],
    worker_results: list[dict],
) -> dict:
    version_tag = model_version or f"model-{model.id[:8]}"
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
            worker_result=worker_by_sample.get(
                sample.id,
                {"sample_id": sample.id, "error": "missing worker result"},
            ),
            model_id=model.id,
            org_id=org_id,
            model_version=version_tag,
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
            payload={
                "successful": successful,
                "failed": failed,
                "processed": len(sample_ids),
            },
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
    container, should_close = await _with_flow_container()
    try:
        return await _run_prediction_job_with_container(
            container=container,
            job_id=job_id,
            dataset_id=dataset_id,
            model_id=model_id,
            org_id=org_id,
            target=target,
            model_version=model_version,
            sample_ids=sample_ids,
            prompt=prompt,
        )
    finally:
        if should_close:
            await container.close()


async def _run_prediction_job_with_container(
    *,
    container,
    job_id: str,
    dataset_id: str,
    model_id: str,
    org_id: str,
    target: str,
    model_version: str | None,
    sample_ids: list[str] | None,
    prompt: str | None = None,
) -> dict:
    repo = container.prediction_repository
    dataset = await repo.get_dataset(dataset_id, org_id)
    if dataset is None:
        raise ValueError(f"Dataset not found: {dataset_id}")

    if sample_ids:
        selected_ids = [
            sid for sid in sample_ids if await repo.get_sample(sid) is not None
        ]
    else:
        selected_ids: list[str] = []
        offset = 0
        page_size = 100
        while True:
            batch, total = await repo.list_samples(
                dataset_id, offset=offset, limit=page_size
            )
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
        PredictionEvent(
            job_id=job_id,
            ts=datetime.now(UTC),
            message="prediction flow running",
            payload={"total_samples": len(selected_ids)},
        )
    )

    chunk_size = 32
    for start in range(0, len(selected_ids), chunk_size):
        current_job = await repo.get_prediction_job(job_id, org_id=org_id)
        if current_job is not None and str(current_job.status) in {
            "cancelled",
            "JobStatus.CANCELLED",
        }:
            summary["completed_at"] = datetime.now(UTC).isoformat()
            summary["cancelled"] = True
            await repo.update_prediction_job_status(
                job_id, JobStatus.CANCELLED, summary=summary
            )
            await repo.add_prediction_event(
                PredictionEvent(
                    job_id=job_id,
                    ts=datetime.now(UTC),
                    message="prediction flow cancelled",
                    payload={"summary": summary},
                )
            )
            return summary
        chunk_ids = selected_ids[start : start + chunk_size]
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
            summary["embedding_model"] = chunk_summary.get(
                "embedding_model", embed_model
            )
        else:
            worker_results = await predict_chunk(
                job_id=job_id,
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
        await repo.update_prediction_job_status(
            job_id, JobStatus.RUNNING, summary=summary
        )

    summary["completed_at"] = datetime.now(UTC).isoformat()
    await repo.update_prediction_job_status(
        job_id, JobStatus.COMPLETED, summary=summary
    )
    await repo.add_prediction_event(
        PredictionEvent(
            job_id=job_id,
            ts=datetime.now(UTC),
            message="prediction flow completed",
            payload={"summary": summary},
        )
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
    container, should_close = await _with_flow_container()
    try:
        result = await _run_prediction_job_with_container(
            container=container,
            job_id=job_id,
            dataset_id=dataset_id,
            model_id=model_id,
            org_id=org_id,
            target=target,
            model_version=model_version,
            sample_ids=sample_ids,
            prompt=prompt,
        )
    finally:
        if should_close:
            await container.close()
    logger.info(
        "Prediction complete: total=%s successful=%s failed=%s",
        result.get("total_samples"),
        result.get("successful"),
        result.get("failed"),
    )
    return result
