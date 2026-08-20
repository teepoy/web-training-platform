from __future__ import annotations

import logging
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from prefect import get_run_logger

from app.modules.datasets.domain.sample_row import PredictionResult
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.runtime.domain.context import (
    PredictionRuntimeContext,
    TrainingRuntimeContext,
)
from app.modules.runtime.domain.events import (
    ArtifactOutput,
    LocalArtifactFile,
    MetricsReported,
    OperationCompleted,
    RuntimeEventStream,
    RuntimeExecutionError,
    RuntimeIssueReported,
)
from app.modules.sc.app.services.sample_filter import (
    parse_and_apply_workflow_sample_filter,
)
from app.modules.sc.app.services.training_selection import (
    limit_sc_training_rows_per_class,
)
from app.modules.sc.capabilities import SC_PATCH_IMAGE_V1
from app.modules.sc.domain.job_image_source import (
    ScJobImageSourceFactory,
)
from app.modules.sc.materialization.port.local import ScInspectionMaterializerPort
from app.modules.sc.runtime.data_source import open_sc_runtime_source
from app.modules.sc.runtime.materialized_input import parquet_paths_from_manifest
from app.modules.sc.runtime.prediction_io import (
    load_sc_prediction_model,
    write_sc_predictions,
)
from app.modules.sc.runtime.streaming_prediction import (
    stream_sc_prediction_image_pairs,
)
from app.modules.training.domain.repository import TrainingRepository
from app.shared.api.schemas import JobStatus, Model, PredictionEvent, TrainingEvent

logger = logging.getLogger(__name__)


def _runtime_logger() -> Any:
    try:
        return get_run_logger()
    except Exception:
        return logger


def _model_artifact_id(job_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"web-training-platform:runtime-artifact:{job_id}:model",
        )
    )


def _model_metadata(
    ctx: TrainingRuntimeContext,
    metadata: dict[str, object],
) -> dict[str, object]:
    from app.modules.runtime.catalog import runtime_catalog

    trainer = runtime_catalog.get_trainer_meta(ctx.trainer_id)
    return {
        **metadata,
        "trainer_id": ctx.trainer_id,
        "model_contract": trainer.output_model.contract,
        "model_schema_version": trainer.output_model.schema_version,
        "predictor_ids": list(trainer.predictor_ids),
        "source_dataset_id": ctx.dataset_id,
        "source_collection_id": ctx.collection_id,
        "source_collection_revision_id": ctx.collection_revision_id,
    }


@dataclass(frozen=True, slots=True)
class ScYoloTrainingResult:
    artifact: ArtifactOutput
    metrics: MetricsReported
    issues: tuple[RuntimeIssueReported, ...]


async def execute_yolo_sc_training(
    ctx: TrainingRuntimeContext,
    *,
    work_dir: Path,
) -> ScYoloTrainingResult:
    import app.registrations  # noqa: F401
    import polars as pl

    from ml_library import inspect_yolo_training_samples, train_yolo

    app_context = ctx.app_context
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    pipeline = app_context.shared.config.sc.pipeline
    training_repository = app_context.injector.get(TrainingRepository)

    async def report_epoch(
        epoch: int,
        total_epochs: int,
        loss: float,
        accuracy: float,
    ) -> None:
        _runtime_logger().info(
            "SC YOLO epoch %d/%d loss=%.6f accuracy=%.6f",
            epoch,
            total_epochs,
            loss,
            accuracy,
        )
        await training_repository.add_event(
            TrainingEvent(
                job_id=ctx.job_id,
                ts=datetime.now(UTC),
                level="epoch",
                message=f"epoch {epoch}/{total_epochs} completed",
                payload={
                    "epoch": epoch,
                    "total_epochs": total_epochs,
                    "loss": loss,
                    "accuracy": accuracy,
                    "progress": epoch / total_epochs,
                },
            )
        )

    async with open_sc_runtime_source(
        ctx,
        with_labels=True,
        with_predictions=ctx.sample_filter is not None,
    ) as source:
        if source.collection_revision_id is not None:
            await training_repository.add_event(
                TrainingEvent(
                    job_id=ctx.job_id,
                    ts=datetime.now(UTC),
                    level="info",
                    message="resolved observed Collection input",
                    payload={
                        "source_resolution": "observed",
                        "reproducibility_capability": False,
                        "collection_revision_id": source.collection_revision_id,
                        "source_dataset_ids": list(source.source_dataset_ids),
                        "resolved_dataset_revision_ids": list(
                            source.resolved_dataset_revision_ids
                        ),
                    },
                )
            )
        if source.dataset_type not in {"image_sc", "image_sc_collection"}:
            raise ValueError(f"SC trainer {ctx.trainer_id!r} requires image_sc data")
        if SC_PATCH_IMAGE_V1.view_id not in source.view_types:
            raise ValueError(
                f"Runtime source does not provide {SC_PATCH_IMAGE_V1.view_id!r}"
            )
        rows = source.rows
        if ctx.sample_filter is not None:
            rows = parse_and_apply_workflow_sample_filter(
                cast(Any, rows),
                ctx.sample_filter,
            )
        rows = limit_sc_training_rows_per_class(rows)
        selected_rows = int(
            (await rows.select(pl.len().alias("rows")).collect_async()).item(0, "rows")
        )
        if selected_rows > pipeline.training_max_rows:
            raise ValueError(
                "SC training selection exceeds configured row budget: "
                f"{selected_rows} > {pipeline.training_max_rows}"
            )

        _runtime_logger().info(
            "Ultralytics SC trainer materializing input: rows=%d",
            selected_rows,
        )
        materializer = app_context.injector.get(ScInspectionMaterializerPort)
        materialization = await materializer.materialize(
            rows_lazyframe=rows,
            image_source_formats=source.image_source_formats,
            direct_dataset_id=source.dataset_id,
            dataset_id=source.source_identity,
            job_id=ctx.job_id,
            image_types=["patch_template", "patch_defective"],
            max_output_bytes=pipeline.training_max_materialized_bytes,
        )
        try:
            work_dir.mkdir(parents=True, exist_ok=True)
            parquet_paths = parquet_paths_from_manifest(materialization.manifest)
            labels, valid_samples, skipped_samples = inspect_yolo_training_samples(
                parquet_paths,
                source.label_space,
            )
            if len(labels) < 2:
                raise RuntimeExecutionError(
                    "sc_training_insufficient_labels_after_image_filter",
                    "SC Ultralytics training requires at least two labels after "
                    "skipping unreadable images",
                    details={
                        "active_labels": list(labels),
                        "skipped_samples": skipped_samples,
                    },
                )
            output = await train_yolo(
                parquet_paths,
                labels,
                valid_samples=valid_samples,
                work_dir=work_dir,
                shuffle_seed=pipeline.training_shuffle_seed,
                shuffle_buffer_rows=pipeline.training_shuffle_buffer_rows,
                on_epoch=report_epoch,
            )
            issues = (
                (
                    RuntimeIssueReported(
                        code="sc_training_images_skipped",
                        message=(
                            "SC Ultralytics training skipped unusable image samples"
                        ),
                        details={
                            "materialization_errors": len(materialization.errors),
                            "unreadable_samples": skipped_samples,
                        },
                    ),
                )
                if materialization.errors or skipped_samples
                else ()
            )
            return ScYoloTrainingResult(
                artifact=ArtifactOutput(
                    id=_model_artifact_id(ctx.job_id),
                    kind="model",
                    payload=LocalArtifactFile(
                        path=output.checkpoint_path,
                        object_name=f"models/{ctx.job_id}/checkpoint.pt",
                        content_type="application/octet-stream",
                    ),
                    metadata=_model_metadata(
                        ctx,
                        {
                            **dict(output.metadata),
                            **(
                                {
                                    "source_resolution": "observed",
                                    "reproducibility_capability": False,
                                    "resolved_dataset_revision_ids": list(
                                        source.resolved_dataset_revision_ids
                                    ),
                                }
                                if source.collection_revision_id is not None
                                else {}
                            ),
                        },
                    ),
                    name="checkpoint.pt",
                    format="pytorch",
                ),
                metrics=MetricsReported(dict(output.metrics)),
                issues=issues,
            )
        finally:
            materialization.cleanup()


async def yolo_sc_train(ctx: TrainingRuntimeContext) -> RuntimeEventStream:
    with tempfile.TemporaryDirectory(
        prefix=f"sc-ultralytics-training-{ctx.job_id}-"
    ) as temporary_directory:
        result = await execute_yolo_sc_training(
            ctx,
            work_dir=Path(temporary_directory),
        )
        for issue in result.issues:
            yield issue
        yield result.artifact
        yield result.metrics
        yield OperationCompleted({"job_id": ctx.job_id, "status": "completed"})


@asynccontextmanager
async def _prediction_checkpoint(
    *,
    app_context: Any,
    model: Model,
    local_checkpoint: Path | None,
    job_id: str,
) -> AsyncIterator[Path]:
    if local_checkpoint is not None:
        if not local_checkpoint.is_file():
            raise FileNotFoundError(
                f"Local SC prediction checkpoint does not exist: {local_checkpoint}"
            )
        yield local_checkpoint
        return
    with tempfile.TemporaryDirectory(
        prefix=f"sc-ultralytics-prediction-{job_id}-"
    ) as temporary_directory:
        checkpoint_path = Path(temporary_directory) / "model.pt"
        await app_context.shared.artifact_storage.get_file(
            model.uri,
            str(checkpoint_path),
        )
        yield checkpoint_path


async def _yolo_sc_predictor(
    ctx: PredictionRuntimeContext,
    *,
    model_override: Model | None = None,
    local_checkpoint: Path | None = None,
) -> RuntimeEventStream:
    import app.registrations  # noqa: F401

    from ml_library import predict_yolo_stream

    from app.modules.runtime.catalog import runtime_catalog

    app_context = ctx.app_context
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    pipeline = app_context.shared.config.sc.pipeline
    model = model_override or await load_sc_prediction_model(ctx)
    model_metadata = model.metadata if isinstance(model.metadata, dict) else {}
    predictor = runtime_catalog.validate_predictor_model_contract(
        ctx.predictor_id,
        model_contract=model_metadata.get("model_contract"),
        model_schema_version=model_metadata.get("model_schema_version"),
    )
    raw_labels = model_metadata.get("label_space", [])
    if not isinstance(raw_labels, Sequence) or isinstance(raw_labels, (str, bytes)):
        raise ValueError("Ultralytics model metadata must include label_space")
    labels = [str(label) for label in raw_labels]
    if not labels:
        raise ValueError("Ultralytics model metadata must include label_space")

    repo = app_context.injector.get(PredictionRepository)
    existing_job = await repo.get_prediction_job(ctx.job_id, ctx.org_id)
    existing_summary = (
        existing_job.summary
        if existing_job is not None and isinstance(existing_job.summary, dict)
        else {}
    )

    async with open_sc_runtime_source(
        ctx,
        with_labels=ctx.sample_filter is not None,
        with_predictions=ctx.sample_filter is not None,
    ) as source:
        if predictor.view_id not in source.view_types:
            raise ValueError(
                f"Predictor {ctx.predictor_id!r} requires view {predictor.view_id!r}, "
                f"runtime source provides {source.view_types}"
            )
        rows = source.rows
        if ctx.sample_filter is not None:
            if source.dataset_type != "image_sc":
                raise ValueError(
                    "sample_filter is only supported for direct image_sc datasets"
                )
            rows = parse_and_apply_workflow_sample_filter(
                cast(Any, rows),
                ctx.sample_filter,
            )
        model_version = ctx.model_version or f"model-{model.id[:8]}"
        summary: dict[str, Any] = {
            **existing_summary,
            "model_id": model.id,
            "dataset_id": source.dataset_id,
            "collection_id": source.collection_id,
            "collection_revision_id": source.collection_revision_id,
            "source_resolution": (
                "observed" if source.collection_revision_id is not None else "current"
            ),
            "reproducibility_capability": False,
            "source_dataset_ids": list(source.source_dataset_ids),
            "resolved_dataset_revision_ids": list(source.resolved_dataset_revision_ids),
            "total_samples": None,
            "successful": 0,
            "failed": 0,
            "processed": 0,
            "started_at": datetime.now(UTC).isoformat(),
            "model_version": model_version,
        }
        await repo.update_prediction_job_status(
            ctx.job_id,
            JobStatus.RUNNING,
            summary=summary,
        )
        last_flush = time.monotonic()

        async def flush_progress(*, force: bool = False) -> None:
            nonlocal last_flush
            processed = int(summary["processed"])
            now = time.monotonic()
            if not (
                force
                or processed % pipeline.prediction_progress_flush_rows == 0
                or now - last_flush >= pipeline.prediction_progress_flush_seconds
            ):
                return
            await repo.update_prediction_job_status(
                ctx.job_id,
                JobStatus.RUNNING,
                summary=dict(summary),
            )
            last_flush = now

        async with _prediction_checkpoint(
            app_context=app_context,
            model=model,
            local_checkpoint=local_checkpoint,
            job_id=ctx.job_id,
        ) as checkpoint_path:
            image_source_factory = app_context.injector.get(ScJobImageSourceFactory)
            async with image_source_factory.open() as image_resolver:
                image_pairs = stream_sc_prediction_image_pairs(
                    rows,
                    image_resolver=image_resolver,
                    image_source_formats=source.image_source_formats,
                    direct_dataset_id=source.dataset_id,
                    input_batch_rows=pipeline.prediction_input_batch_rows,
                )

                async def prediction_results():
                    async for output in predict_yolo_stream(
                        checkpoint_path,
                        labels,
                        image_pairs,
                        workers=pipeline.prediction_preprocess_workers,
                        preprocess_task_size=pipeline.prediction_preprocess_task_rows,
                        prefetch_tasks=pipeline.prediction_preprocess_prefetch_tasks,
                    ):
                        result = PredictionResult(
                            sample_id=output.sample_id,
                            predicted_label=output.label,
                            confidence=output.confidence,
                            all_scores=(dict(output.scores) if output.scores else None),
                            model_id=model.id,
                            target=ctx.target,
                            model_version=model_version,
                            job_id=ctx.job_id,
                            error=output.error,
                        )
                        summary["failed" if result.error else "successful"] += 1
                        summary["processed"] += 1
                        yield result
                        await flush_progress()

                await write_sc_predictions(
                    runtime_ctx=ctx,
                    source=source,
                    predictions=prediction_results(),
                    model_id=model.id,
                    model_version=model_version,
                    batch_size=pipeline.prediction_write_batch_rows,
                )
        summary["total_samples"] = int(summary["processed"])
        source_dataset_ids = source.source_dataset_ids

    publisher = app_context.shared.redis_event_publisher
    if publisher is not None:
        for dataset_id in source_dataset_ids:
            await publisher.publish_prediction_refresh(
                dataset_id=dataset_id,
                job_id=ctx.job_id,
            )
    summary["completed_at"] = datetime.now(UTC).isoformat()
    await flush_progress(force=True)
    await repo.update_prediction_job_status(
        ctx.job_id,
        JobStatus.COMPLETED,
        summary=summary,
    )
    await repo.add_prediction_event(
        PredictionEvent(
            job_id=ctx.job_id,
            ts=datetime.now(UTC),
            message="SC Ultralytics prediction completed",
            payload={"summary": summary},
        )
    )
    failed = int(summary["failed"])
    if failed:
        yield RuntimeIssueReported(
            code="sc_prediction_samples_failed",
            message="SC Ultralytics prediction completed with failed samples",
            details={"failed": failed, "processed": int(summary["processed"])},
        )
    yield OperationCompleted(summary)


async def yolo_sc_predictor(ctx: PredictionRuntimeContext) -> RuntimeEventStream:
    async for event in _yolo_sc_predictor(ctx):
        yield event


async def yolo_sc_predictor_from_local_checkpoint(
    ctx: PredictionRuntimeContext,
    *,
    model: Model,
    checkpoint_path: Path,
) -> RuntimeEventStream:
    async for event in _yolo_sc_predictor(
        ctx,
        model_override=model,
        local_checkpoint=checkpoint_path,
    ):
        yield event


__all__ = [
    "ScYoloTrainingResult",
    "execute_yolo_sc_training",
    "yolo_sc_predictor",
    "yolo_sc_predictor_from_local_checkpoint",
    "yolo_sc_train",
]
