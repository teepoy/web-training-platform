from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.runtime.app.services.artifact_output_sink import (
    PlatformArtifactOutputSink,
)
from app.modules.runtime.domain.context import (
    PredictionRuntimeContext,
    TrainAndPredictRuntimeContext,
    TrainingRuntimeContext,
)
from app.modules.runtime.domain.events import (
    OperationCompleted,
    RuntimeEventStream,
    collect_runtime_events,
)
from app.modules.training.domain.repository import TrainingRepository
from app.shared.api.schemas import (
    JobStatus,
    PredictionEvent,
    PredictionJob,
    TrainingEvent,
)


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


def _model_artifact_id(training_result: dict[str, object]) -> str:
    artifacts = training_result.get("artifacts")
    if not isinstance(artifacts, list):
        raise RuntimeError("Training completed without artifacts")
    model_ids = [
        str(artifact.get("id"))
        for artifact in artifacts
        if isinstance(artifact, dict)
        and artifact.get("kind") == "model"
        and artifact.get("id")
    ]
    if len(model_ids) != 1:
        raise RuntimeError(
            "Training must produce exactly one model artifact, "
            f"received {len(model_ids)}"
        )
    return model_ids[0]


async def run_sc_train_and_predict(
    ctx: TrainAndPredictRuntimeContext,
) -> RuntimeEventStream:
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
        training = await collect_runtime_events(
            runtime_catalog.stream_train(
                ctx.trainer_id,
                TrainingRuntimeContext(
                    app_context=ctx.app_context,
                    job_id=ctx.job_id,
                    dataset_id=ctx.dataset_id,
                    trainer_id=ctx.trainer_id,
                    created_by=ctx.created_by,
                    sample_ids=ctx.sample_ids,
                    sample_filter=ctx.sample_filter,
                    org_id=ctx.org_id,
                    collection_id=ctx.collection_id,
                    collection_revision_id=ctx.collection_revision_id,
                ),
            ),
            artifact_sink=PlatformArtifactOutputSink(
                storage=ctx.app_context.shared.artifact_storage,
                repository=training_repository,
                job_id=ctx.job_id,
            ),
        )
        model_id = _model_artifact_id(training)
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
        prediction = await collect_runtime_events(
            runtime_catalog.stream_predict(
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
    yield OperationCompleted(
        {
            "job_id": ctx.job_id,
            "prediction_job_id": prediction_job.id,
            "model_id": model_id,
            "training": training,
            "prediction": prediction,
        }
    )


__all__ = ["run_sc_train_and_predict"]
