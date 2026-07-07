from __future__ import annotations
# pyright: reportMissingImports=false

from datetime import UTC, datetime
from typing import Any

from prefect import flow, get_run_logger, task
from sqlalchemy import select

from app.composition import build_flow_container
from app.core.config import load_config
from app.modules.prediction.flows.predict_job import _run_prediction_job_with_container
from app.modules.training.flows.train_job import run_training_pipeline
from app.shared.api.schemas import (
    JobStatus,
    PredictionEvent,
    PredictionJob,
    TrainingEvent,
)
from app.shared.db.models.artifacts import ArtifactORM


async def _add_training_event(container: Any, event: TrainingEvent) -> None:
    await container.training_orchestrator.repository.add_event(event)


async def _latest_model_artifact_id(container: Any, job_id: str) -> str | None:
    async with container.session_factory() as session:
        stmt = (
            select(ArtifactORM)
            .where(ArtifactORM.job_id == job_id)
            .where(ArtifactORM.kind == "model")
            .order_by(ArtifactORM.created_at.desc())
        )
        row = (await session.execute(stmt)).scalars().first()
        return row.id if row is not None else None


@task(name="train-stage")
async def train_stage(
    job_id: str,
    dataset_id: str,
    trainer_id: str,
    sample_ids: list[str] | None = None,
) -> dict[str, Any]:
    logger = get_run_logger()
    cfg = load_config(skip_runtime_validation=True)
    container = build_flow_container(cfg)
    try:
        await container.training_orchestrator.repository.update_job_status(
            job_id, JobStatus.RUNNING
        )
        await _add_training_event(
            container,
            TrainingEvent(
                job_id=job_id,
                ts=datetime.now(UTC),
                message="train stage started",
                payload={"status": JobStatus.RUNNING.value},
            ),
        )
        train_result = await run_training_pipeline(
            job_id=job_id,
            dataset_id=dataset_id,
            trainer_id=trainer_id,
            sample_ids=sample_ids,
        )
        model_id = await _latest_model_artifact_id(container, job_id)
        if model_id is None:
            raise RuntimeError("Training completed without a model artifact")
        await container.training_orchestrator.repository.update_job_status(
            job_id, JobStatus.COMPLETED
        )
        await _add_training_event(
            container,
            TrainingEvent(
                job_id=job_id,
                ts=datetime.now(UTC),
                message="train stage completed",
                payload={"status": JobStatus.COMPLETED.value, "model_id": model_id},
            ),
        )
        return {"model_id": model_id, "training": train_result}
    except Exception as exc:
        logger.exception("train stage failed: job_id=%s", job_id)
        await container.training_orchestrator.repository.update_job_status(
            job_id, JobStatus.FAILED
        )
        await _add_training_event(
            container,
            TrainingEvent(
                job_id=job_id,
                ts=datetime.now(UTC),
                message="train stage failed",
                payload={"status": JobStatus.FAILED.value, "error": str(exc)},
            ),
        )
        raise
    finally:
        await container.close()


@task(name="predict-stage")
async def predict_stage(
    source_training_job_id: str,
    dataset_id: str,
    model_id: str,
    org_id: str,
    created_by: str,
    target: str,
    model_version: str | None,
    sample_ids: list[str] | None,
    prompt: str | None,
) -> dict[str, Any]:
    logger = get_run_logger()
    cfg = load_config(skip_runtime_validation=True)
    container = build_flow_container(cfg)
    try:
        await _add_training_event(
            container,
            TrainingEvent(
                job_id=source_training_job_id,
                ts=datetime.now(UTC),
                message="predict stage started",
                payload={"model_id": model_id},
            ),
        )
        prediction_job = PredictionJob(
            dataset_id=dataset_id,
            model_id=model_id,
            created_by=created_by,
            target=target,
            model_version=model_version,
            org_id=org_id,
            sample_ids=sample_ids,
            summary={
                "source_training_job_id": source_training_job_id,
                **({"prompt": prompt} if prompt else {}),
            },
        )
        prediction_job = await container.prediction_repository.create_prediction_job(
            prediction_job, org_id=org_id
        )
        await container.prediction_repository.add_prediction_event(
            PredictionEvent(
                job_id=prediction_job.id,
                ts=datetime.now(UTC),
                message="prediction job created by train-and-predict workflow",
                payload={
                    "source_training_job_id": source_training_job_id,
                    "model_id": model_id,
                },
            )
        )
        prediction_summary = await _run_prediction_job_with_container(
            container=container,
            job_id=prediction_job.id,
            dataset_id=dataset_id,
            model_id=model_id,
            org_id=org_id,
            target=target,
            model_version=model_version,
            sample_ids=sample_ids,
            prompt=prompt,
        )
        await _add_training_event(
            container,
            TrainingEvent(
                job_id=source_training_job_id,
                ts=datetime.now(UTC),
                message="predict stage completed",
                payload={"prediction_job_id": prediction_job.id},
            ),
        )
        logger.info(
            "predict stage complete: train_job=%s prediction_job=%s",
            source_training_job_id,
            prediction_job.id,
        )
        return {
            "prediction_job_id": prediction_job.id,
            "prediction": prediction_summary,
        }
    finally:
        await container.close()


@flow(name="training-train-and-predict")
async def train_and_predict_flow(
    job_id: str,
    dataset_id: str,
    trainer_id: str,
    org_id: str,
    created_by: str = "system",
    target: str = "image_classification",
    model_version: str | None = None,
    sample_ids: list[str] | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    import app.registrations  # noqa: F401

    logger = get_run_logger()
    train_result = await train_stage(
        job_id=job_id,
        dataset_id=dataset_id,
        trainer_id=trainer_id,
        sample_ids=sample_ids,
    )
    model_id = str(train_result["model_id"])
    prediction_result = await predict_stage(
        source_training_job_id=job_id,
        dataset_id=dataset_id,
        model_id=model_id,
        org_id=org_id,
        created_by=created_by,
        target=target,
        model_version=model_version,
        sample_ids=sample_ids,
        prompt=prompt,
    )
    logger.info(
        "train-and-predict complete: train_job=%s prediction_job=%s",
        job_id,
        prediction_result["prediction_job_id"],
    )
    return {
        "job_id": job_id,
        "prediction_job_id": prediction_result["prediction_job_id"],
        "model_id": model_id,
        "training": train_result["training"],
        "prediction": prediction_result["prediction"],
    }


__all__ = ["predict_stage", "train_and_predict_flow", "train_stage"]
