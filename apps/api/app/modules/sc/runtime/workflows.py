from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.runtime.domain.context import (
    PredictionRuntimeContext,
    TrainAndPredictRuntimeContext,
    TrainingRuntimeContext,
)
from app.modules.runtime.domain.executables import RuntimeOperation
from app.modules.sc.runtime.router import SC_RUNTIME_ROUTER
from app.modules.training.domain.repository import TrainingRepository
from app.shared.api.schemas import (
    JobStatus,
    PredictionEvent,
    PredictionJob,
    TrainingEvent,
)
from app.shared.db.models.artifacts import ArtifactORM


async def _add_training_event(
    repository: TrainingRepository,
    *,
    job_id: str,
    message: str,
    payload: dict[str, Any],
    level: str = "info",
) -> None:
    await repository.add_event(
        TrainingEvent(
            job_id=job_id,
            ts=datetime.now(UTC),
            level=level,
            message=message,
            payload=payload,
        )
    )


async def _latest_model_artifact_id(
    ctx: TrainAndPredictRuntimeContext,
) -> str:
    async with ctx.app_context.shared.session_factory() as session:
        stmt = (
            select(ArtifactORM)
            .where(ArtifactORM.job_id == ctx.job_id)
            .where(ArtifactORM.kind == "model")
            .order_by(ArtifactORM.created_at.desc())
        )
        row = (await session.execute(stmt)).scalars().first()
        if row is None:
            raise RuntimeError("Training completed without a model artifact")
        return row.id


async def _run_sc_train_and_predict(
    ctx: TrainAndPredictRuntimeContext,
) -> dict[str, Any]:
    from app.modules.runtime.catalog import runtime_catalog

    if ctx.app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    training_repository = ctx.app_context.injector.get(TrainingRepository)
    prediction_repository = ctx.app_context.injector.get(PredictionRepository)
    await training_repository.update_job_status(ctx.job_id, JobStatus.RUNNING)
    await _add_training_event(
        training_repository,
        job_id=ctx.job_id,
        message="SC training started",
        payload={"status": JobStatus.RUNNING.value},
    )
    try:
        training = await runtime_catalog.invoke(
            RuntimeOperation.TRAIN,
            ctx.trainer_id,
            TrainingRuntimeContext(
                app_context=ctx.app_context,
                job_id=ctx.job_id,
                dataset_id=ctx.dataset_id,
                trainer_id=ctx.trainer_id,
                created_by=ctx.created_by,
                sample_ids=ctx.sample_ids,
                sample_filter=ctx.sample_filter,
                missing_image_policy=ctx.missing_image_policy,
                org_id=ctx.org_id,
                collection_id=ctx.collection_id,
                collection_revision_id=ctx.collection_revision_id,
            ),
        )
        model_id = await _latest_model_artifact_id(ctx)
        await training_repository.update_job_status(ctx.job_id, JobStatus.COMPLETED)
        await _add_training_event(
            training_repository,
            job_id=ctx.job_id,
            message="SC training completed",
            payload={"status": JobStatus.COMPLETED.value, "model_id": model_id},
        )
    except Exception as exc:
        await training_repository.update_job_status(ctx.job_id, JobStatus.FAILED)
        await _add_training_event(
            training_repository,
            job_id=ctx.job_id,
            message="SC training failed",
            payload={"status": JobStatus.FAILED.value, "error": str(exc)},
            level="error",
        )
        raise

    prediction_job = await prediction_repository.create_prediction_job(
        PredictionJob(
            dataset_id=ctx.dataset_id,
            collection_id=ctx.collection_id,
            collection_revision_id=ctx.collection_revision_id,
            model_id=model_id,
            created_by=ctx.created_by,
            target=ctx.target,
            model_version=ctx.model_version,
            org_id=ctx.org_id,
            sample_ids=ctx.sample_ids,
            summary={
                "source_training_job_id": ctx.job_id,
                "result_pool": "validation",
                **(
                    {"sample_filter": ctx.sample_filter}
                    if ctx.sample_filter is not None
                    else {}
                ),
                **({"prompt": ctx.prompt} if ctx.prompt else {}),
            },
        ),
        org_id=ctx.org_id,
    )
    await prediction_repository.add_prediction_event(
        PredictionEvent(
            job_id=prediction_job.id,
            ts=datetime.now(UTC),
            message="prediction job created by SC train-and-predict",
            payload={"source_training_job_id": ctx.job_id, "model_id": model_id},
        )
    )
    try:
        prediction = await runtime_catalog.invoke(
            RuntimeOperation.PREDICT,
            ctx.predictor_id,
            PredictionRuntimeContext(
                app_context=ctx.app_context,
                job_id=prediction_job.id,
                dataset_id=ctx.dataset_id,
                model_id=model_id,
                org_id=ctx.org_id,
                predictor_id=ctx.predictor_id,
                created_by=ctx.created_by,
                target=ctx.target,
                model_version=ctx.model_version,
                sample_ids=ctx.sample_ids,
                sample_filter=ctx.sample_filter,
                prompt=ctx.prompt,
                collection_id=ctx.collection_id,
                collection_revision_id=ctx.collection_revision_id,
            ),
        )
    except Exception as exc:
        failure = {
            **prediction_job.summary,
            "source_training_job_id": ctx.job_id,
            "model_id": model_id,
            "error": str(exc),
            "retryable": True,
        }
        await prediction_repository.update_prediction_job_status(
            prediction_job.id,
            JobStatus.FAILED,
            summary=failure,
        )
        await _add_training_event(
            training_repository,
            job_id=ctx.job_id,
            message="SC prediction failed; trained model remains available",
            payload={
                "status": JobStatus.COMPLETED.value,
                "model_id": model_id,
                "prediction_job_id": prediction_job.id,
                "prediction_status": JobStatus.FAILED.value,
                "error": str(exc),
                "retryable": True,
            },
            level="error",
        )
        raise
    await _add_training_event(
        training_repository,
        job_id=ctx.job_id,
        message="SC prediction completed",
        payload={"prediction_job_id": prediction_job.id},
    )
    return {
        "job_id": ctx.job_id,
        "prediction_job_id": prediction_job.id,
        "model_id": model_id,
        "training": training,
        "prediction": prediction,
    }


@SC_RUNTIME_ROUTER.train_and_predict(trainer_id="resnet50-sc-v1")
async def resnet_sc_train_and_predict(
    ctx: TrainAndPredictRuntimeContext,
) -> dict[str, Any]:
    return await _run_sc_train_and_predict(ctx)


@SC_RUNTIME_ROUTER.train_and_predict(trainer_id="yolo-sc-v1")
async def yolo_sc_train_and_predict(
    ctx: TrainAndPredictRuntimeContext,
) -> dict[str, Any]:
    return await _run_sc_train_and_predict(ctx)


__all__ = ["resnet_sc_train_and_predict", "yolo_sc_train_and_predict"]
