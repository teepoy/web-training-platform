from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prefect import task

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
    LocalArtifactFile,
    OperationCompleted,
    RuntimeEventStream,
    collect_runtime_events,
)
from app.modules.sc.runtime.ultralytics import (
    ScYoloTrainingResult,
    execute_yolo_sc_training,
    yolo_sc_predictor_from_local_checkpoint,
)
from app.modules.training.domain.repository import TrainingRepository
from app.shared.api.schemas import (
    ArtifactRef,
    JobStatus,
    Model,
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


def _local_model(
    ctx: TrainAndPredictRuntimeContext,
    training: ScYoloTrainingResult,
) -> tuple[Model, Path]:
    payload = training.artifact.payload
    if not isinstance(payload, LocalArtifactFile):
        raise RuntimeError("SC training must produce one local checkpoint file")
    return (
        Model(
            id=training.artifact.id,
            uri=f"local://{payload.path}",
            kind=training.artifact.kind,
            metadata=dict(training.artifact.metadata),
            name=training.artifact.name,
            format=training.artifact.format,
            job_id=ctx.job_id,
            dataset_id=ctx.dataset_id,
            collection_id=ctx.collection_id,
            collection_revision_id=ctx.collection_revision_id,
            trainer_id=ctx.trainer_id,
            created_by=ctx.created_by,
        ),
        payload.path,
    )


def _training_result(
    training: ScYoloTrainingResult,
    artifact: ArtifactRef,
    *,
    job_id: str,
) -> dict[str, object]:
    artifact_payload = artifact.model_dump(mode="json")
    return {
        "job_id": job_id,
        "status": "completed",
        "artifacts": [artifact_payload],
        "metrics": dict(training.metrics.metrics),
        **(
            {
                "issues": [
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "details": dict(issue.details),
                    }
                    for issue in training.issues
                ]
            }
            if training.issues
            else {}
        ),
    }


async def run_sc_train_and_predict(
    ctx: TrainAndPredictRuntimeContext,
) -> RuntimeEventStream:
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
    training_context = TrainingRuntimeContext(
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
    )
    with tempfile.TemporaryDirectory(
        prefix=f"sc-train-predict-{ctx.job_id}-"
    ) as temporary_directory:

        @task(name="sc-train", persist_result=False)
        async def train_task() -> ScYoloTrainingResult:
            return await execute_yolo_sc_training(
                training_context,
                work_dir=Path(temporary_directory) / "training",
            )

        try:
            training_execution = await train_task()
            model, checkpoint_path = _local_model(ctx, training_execution)
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

        async def persist_model() -> ArtifactRef:
            try:
                artifact = await PlatformArtifactOutputSink(
                    storage=ctx.app_context.shared.artifact_storage,
                    repository=training_repository,
                    job_id=ctx.job_id,
                ).persist(training_execution.artifact)
            except Exception as exc:
                await training_repository.update_job_status(
                    ctx.job_id, JobStatus.FAILED
                )
                await _add_training_event(
                    training_repository,
                    job_id=ctx.job_id,
                    message="SC model upload failed",
                    payload={"status": JobStatus.FAILED.value, "error": str(exc)},
                    level="error",
                )
                raise
            await training_repository.update_job_status(ctx.job_id, JobStatus.COMPLETED)
            await _add_training_event(
                training_repository,
                job_id=ctx.job_id,
                message="SC training completed",
                payload={
                    "status": JobStatus.COMPLETED.value,
                    "model_id": model.id,
                },
            )
            return artifact

        upload_task = asyncio.create_task(
            persist_model(),
            name=f"upload-sc-checkpoint-{ctx.job_id}",
        )
        await asyncio.sleep(0)

        prediction_job = await prediction_repository.create_prediction_job(
            PredictionJob(
                dataset_id=ctx.dataset_id,
                collection_id=ctx.collection_id,
                collection_revision_id=ctx.collection_revision_id,
                model_id=model.id,
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
                payload={
                    "source_training_job_id": ctx.job_id,
                    "model_id": model.id,
                },
            )
        )
        prediction_context = PredictionRuntimeContext(
            app_context=ctx.app_context,
            job_id=prediction_job.id,
            dataset_id=ctx.dataset_id,
            model_id=model.id,
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
        )

        @task(name="sc-predict", persist_result=False)
        async def predict_task() -> dict[str, object]:
            return await collect_runtime_events(
                yolo_sc_predictor_from_local_checkpoint(
                    prediction_context,
                    model=model,
                    checkpoint_path=checkpoint_path,
                )
            )

        prediction: dict[str, object] | None = None
        prediction_error: Exception | None = None
        try:
            prediction = await predict_task()
        except Exception as exc:
            prediction_error = exc

        artifact = await upload_task
        training = _training_result(
            training_execution,
            artifact,
            job_id=ctx.job_id,
        )
        if prediction_error is not None:
            failure = {
                **prediction_job.summary,
                "source_training_job_id": ctx.job_id,
                "model_id": model.id,
                "error": str(prediction_error),
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
                    "model_id": model.id,
                    "prediction_job_id": prediction_job.id,
                    "prediction_status": JobStatus.FAILED.value,
                    "error": str(prediction_error),
                    "retryable": True,
                },
                level="error",
            )
            raise prediction_error
        if prediction is None:
            raise RuntimeError("SC prediction task returned no result")
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
                "model_id": model.id,
                "training": training,
                "prediction": prediction,
            }
        )


__all__ = ["run_sc_train_and_predict"]
