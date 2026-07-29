from __future__ import annotations
# pyright: reportMissingImports=false

from datetime import UTC, datetime
from typing import Any

from prefect import flow, get_run_logger, task
from sqlalchemy import select

from app.composition import build_flow_app_context, close_flow_app_context
from app.core.config import load_config
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.prediction.flows.predict_job import _run_prediction_job_with_context
from app.modules.training.domain.repository import TrainingRepository
from app.modules.training.flows.train_job import run_training_pipeline
from app.shared.api.schemas import (
    JobStatus,
    PredictionEvent,
    PredictionJob,
    TrainingEvent,
)
from app.shared.db.models.artifacts import ArtifactORM
from app.shared.context import AppContext


async def _add_training_event(ctx: AppContext, event: TrainingEvent) -> None:
    if ctx.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    await ctx.injector.get(TrainingRepository).add_event(event)


async def _latest_model_artifact_id(ctx: AppContext, job_id: str) -> str | None:
    async with ctx.shared.session_factory() as session:
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
    sample_filter: dict[str, Any] | None = None,
    missing_image_policy: str | None = None,
) -> dict[str, Any]:
    logger = get_run_logger()
    cfg = load_config(skip_runtime_validation=True)
    app_context = build_flow_app_context(cfg)
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    training_repository = app_context.injector.get(TrainingRepository)
    try:
        await training_repository.update_job_status(job_id, JobStatus.RUNNING)
        await _add_training_event(
            app_context,
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
            sample_filter=sample_filter,
            missing_image_policy=missing_image_policy,
            app_context=app_context,
        )
        model_id = await _latest_model_artifact_id(app_context, job_id)
        if model_id is None:
            raise RuntimeError("Training completed without a model artifact")
        await training_repository.update_job_status(job_id, JobStatus.COMPLETED)
        await _add_training_event(
            app_context,
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
        await training_repository.update_job_status(job_id, JobStatus.FAILED)
        await _add_training_event(
            app_context,
            TrainingEvent(
                job_id=job_id,
                ts=datetime.now(UTC),
                message="train stage failed",
                payload={"status": JobStatus.FAILED.value, "error": str(exc)},
            ),
        )
        raise
    finally:
        await close_flow_app_context(app_context)


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
    sample_filter: dict[str, Any] | None,
    prompt: str | None,
    predictor_id: str,
) -> dict[str, Any]:
    logger = get_run_logger()
    cfg = load_config(skip_runtime_validation=True)
    app_context = build_flow_app_context(cfg)
    try:
        if app_context.injector is None:
            raise RuntimeError("AppContext injector was not initialized")
        prediction_repository = app_context.injector.get(PredictionRepository)
        await _add_training_event(
            app_context,
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
                **({"sample_filter": sample_filter} if sample_filter else {}),
                **({"prompt": prompt} if prompt else {}),
            },
        )
        prediction_job = await prediction_repository.create_prediction_job(
            prediction_job, org_id=org_id
        )
        await prediction_repository.add_prediction_event(
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
        try:
            prediction_summary = await _run_prediction_job_with_context(
                app_context=app_context,
                job_id=prediction_job.id,
                dataset_id=dataset_id,
                model_id=model_id,
                org_id=org_id,
                target=target,
                model_version=model_version,
                sample_ids=sample_ids,
                sample_filter=sample_filter,
                prompt=prompt,
                requested_predictor_id=predictor_id,
            )
        except Exception as exc:
            logger.exception(
                "predict stage failed: train_job=%s prediction_job=%s",
                source_training_job_id,
                prediction_job.id,
            )
            failure_summary = {
                **prediction_job.summary,
                "source_training_job_id": source_training_job_id,
                "model_id": model_id,
                "error": str(exc),
                "retryable": True,
            }
            await prediction_repository.update_prediction_job_status(
                prediction_job.id,
                JobStatus.FAILED,
                summary=failure_summary,
            )
            await prediction_repository.add_prediction_event(
                PredictionEvent(
                    job_id=prediction_job.id,
                    ts=datetime.now(UTC),
                    level="error",
                    message="predict stage failed after training completed",
                    payload=failure_summary,
                )
            )
            await _add_training_event(
                app_context,
                TrainingEvent(
                    job_id=source_training_job_id,
                    ts=datetime.now(UTC),
                    level="error",
                    message="predict stage failed; trained model remains available",
                    payload={
                        "status": JobStatus.COMPLETED.value,
                        "model_id": model_id,
                        "prediction_job_id": prediction_job.id,
                        "prediction_status": JobStatus.FAILED.value,
                        "error": str(exc),
                        "retryable": True,
                    },
                ),
            )
            raise
        await _add_training_event(
            app_context,
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
        await close_flow_app_context(app_context)


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
    sample_filter: dict[str, Any] | None = None,
    prompt: str | None = None,
    predictor_id: str | None = None,
    catalog_id: str | None = None,
    input_contract: str | None = None,
    output_contract: str | None = None,
    resource_profile: str | None = None,
    owner: str | None = None,
    algo_id: str | None = None,
    algo_version: str | None = None,
    code_version: str | None = None,
    missing_image_policy: str | None = None,
) -> dict[str, Any]:
    import app.registrations  # noqa: F401
    from app.modules.types import catalog

    logger = get_run_logger()
    if owner != "local_compat":
        raise ValueError(
            "API-local train-and-predict flow requires owner='local_compat'"
        )
    if catalog_id is None or catalog_id != trainer_id:
        raise ValueError(
            "Train-and-predict flow requires catalog_id matching trainer_id"
        )
    trainer_metadata = catalog.get_trainer_meta(trainer_id)
    resolved_predictor_id = catalog.resolve_predictor_id(
        trainer_id,
        requested_predictor_id=predictor_id,
    )
    if input_contract != trainer_metadata.input_view.contract:
        raise ValueError(
            f"Train-and-predict input_contract={input_contract!r} does not match "
            f"trainer view contract={trainer_metadata.input_view.contract!r}"
        )
    if missing_image_policy not in {"fail", "skip"}:
        raise ValueError(
            "Train-and-predict missing_image_policy must be explicitly 'fail' or 'skip'"
        )
    logger.info(
        "train-and-predict route: catalog=%s input=%s output=%s profile=%s algo=%s@%s code=%s missing_image_policy=%s",
        catalog_id,
        input_contract,
        output_contract,
        resource_profile,
        algo_id,
        algo_version,
        code_version,
        missing_image_policy,
    )
    train_result = await train_stage(
        job_id=job_id,
        dataset_id=dataset_id,
        trainer_id=trainer_id,
        sample_ids=sample_ids,
        sample_filter=sample_filter,
        missing_image_policy=missing_image_policy,
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
        sample_filter=sample_filter,
        prompt=prompt,
        predictor_id=resolved_predictor_id,
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
