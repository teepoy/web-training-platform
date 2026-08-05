from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from collections.abc import Generator, Iterator, Sequence
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from typing import Any, Callable, cast

from prefect import get_run_logger
from sqlalchemy import or_, select

from app.modules.datasets.domain.sample_row import (
    PredictionResult as StoragePredictionResult,
)
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.runtime.domain.context import PredictionRuntimeContext
from app.modules.runtime.domain.executables import (
    RuntimeOperation,
    RuntimeRouteDefinition,
)
from app.modules.sc.app.services.sample_filter import (
    parse_and_apply_workflow_sample_filter,
)
from app.modules.sc.capabilities import (
    SC_PATCH_IMAGE_V1,
    SC_RESNET_MODEL_V1,
    SC_YOLO_MODEL_V1,
)
from app.modules.sc.materialization.port.local import ScInspectionMaterializerPort
from app.modules.sc.runtime.materialized_input import parquet_paths_from_manifest
from app.modules.sc.runtime.router import SC_RUNTIME_ROUTER
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.api.schemas import (
    Dataset,
    DatasetStorageMode,
    JobStatus,
    Model,
    PredictionEvent,
    TaskSpec,
)
from app.shared.db.models import ArtifactORM, DatasetORM, TrainingJobORM
from app.shared.domain.data_plane import DataPlaneManifest

logger = logging.getLogger(__name__)


def _runtime_logger() -> Any:
    try:
        return get_run_logger()
    except Exception:
        return logger


def _prediction_route() -> tuple[RuntimeRouteDefinition, ...]:
    return (
        RuntimeRouteDefinition(
            operation=RuntimeOperation.PREDICT,
            deployment="predict-job-batch-deployment",
            resource_profile="gpu",
            owner="local_compat",
            missing_image_policy="skip",
            output_contract="sample.predictions.v1",
        ),
    )


async def _load_dataset(
    ctx: PredictionRuntimeContext,
) -> Dataset:
    async with ctx.app_context.shared.session_factory() as session:
        row = await session.get(DatasetORM, ctx.dataset_id)
        if row is None or (row.org_id != ctx.org_id and not row.is_public):
            raise ValueError(f"Dataset not found: {ctx.dataset_id}")
        return Dataset(
            id=row.id,
            org_id=row.org_id,
            name=row.name,
            dataset_type=row.dataset_type,
            task_spec=TaskSpec.model_validate(row.dataset_meta or {}),
            view_types=cast(list[str], row.view_types),
            is_public=row.is_public,
            created_at=row.created_at,
            embed_config=row.embed_config or {},
            ls_project_id=row.ls_project_id,
            storage_mode=DatasetStorageMode(row.storage_mode),
        )


async def _load_model(ctx: PredictionRuntimeContext) -> Model:
    async with ctx.app_context.shared.session_factory() as session:
        stmt = (
            select(ArtifactORM, TrainingJobORM, DatasetORM)
            .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
            .join(DatasetORM, TrainingJobORM.dataset_id == DatasetORM.id)
            .where(ArtifactORM.id == ctx.model_id)
            .where(ArtifactORM.kind == "model")
            .where(
                or_(
                    TrainingJobORM.org_id == ctx.org_id,
                    TrainingJobORM.is_public.is_(True),
                )
            )
        )
        row = (await session.execute(stmt)).first()
        if row is None:
            raise ValueError(f"Model not found: {ctx.model_id}")
        artifact, job, dataset = row
        return Model(
            id=artifact.id,
            uri=artifact.uri,
            kind=artifact.kind,
            metadata=artifact.metadata_json,
            name=artifact.name,
            file_size=artifact.file_size,
            file_hash=artifact.file_hash,
            format=artifact.format,
            created_at=artifact.created_at,
            job_id=artifact.job_id,
            dataset_id=job.dataset_id,
            dataset_name=dataset.name,
            trainer_id=job.trainer_id,
            trainer_name=job.trainer_id,
        )


def _checkpoint_bytes(artifact_storage: Any, uri: str) -> bytes:
    async def fetch() -> bytes:
        return cast(bytes, await artifact_storage.get_bytes(uri))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            lambda: asyncio.new_event_loop().run_until_complete(fetch())
        ).result()


def _prediction_samples(manifest: DataPlaneManifest) -> Iterator[Any]:
    from ml_library import PredictionSample
    from ml_library.data_loading import collect_parquet_dataset

    dataset = collect_parquet_dataset(parquet_paths_from_manifest(manifest))
    for row in dataset:
        yield PredictionSample(
            sample_id=str(row["sample_id"]),
            defective_image=(
                bytes(cast(bytes, row["patch_defective_bytes"]))
                if row.get("patch_defective_bytes") is not None
                else None
            ),
            reference_image=(
                bytes(cast(bytes, row["patch_template_bytes"]))
                if row.get("patch_template_bytes") is not None
                else None
            ),
        )


def _predict_rows(
    *,
    artifact_storage: Any,
    model_uri: str,
    materialization_manifest: DataPlaneManifest,
    kernel: Callable[..., Any],
    label_space: Sequence[str] | None,
) -> Generator[dict[str, Any], None, None]:
    if not model_uri:
        raise ValueError("model URI is required")
    checkpoint = _checkpoint_bytes(artifact_storage, model_uri)
    samples = _prediction_samples(materialization_manifest)
    outputs = (
        kernel(checkpoint, list(label_space), samples)
        if label_space is not None
        else kernel(checkpoint, samples)
    )
    for output in outputs:
        result: dict[str, Any] = {
            "sample_id": output.sample_id,
            "label": output.label,
            "confidence": output.confidence,
        }
        if output.scores:
            result["scores"] = dict(output.scores)
        if output.error is not None:
            result["error"] = output.error
        yield result


async def _run_sc_prediction(
    runtime_ctx: PredictionRuntimeContext,
    *,
    kernel: Callable[..., Any],
    require_model_labels: bool,
) -> dict[str, Any]:
    import app.registrations  # noqa: F401
    import polars as pl

    from app.modules.runtime.catalog import runtime_catalog

    app_context = runtime_ctx.app_context
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    dataset = await _load_dataset(runtime_ctx)
    model = await _load_model(runtime_ctx)
    if model.dataset_id != dataset.id:
        raise ValueError(
            f"Model {model.id!r} belongs to dataset {model.dataset_id!r}, "
            f"not {dataset.id!r}"
        )
    model_metadata = model.metadata if isinstance(model.metadata, dict) else {}
    predictor_metadata = runtime_catalog.validate_predictor_model_contract(
        runtime_ctx.predictor_id,
        model_contract=model_metadata.get("model_contract"),
        model_schema_version=model_metadata.get("model_schema_version"),
    )
    if predictor_metadata.view_id not in dataset.view_types:
        raise ValueError(
            f"Predictor {runtime_ctx.predictor_id!r} requires view "
            f"{predictor_metadata.view_id!r}, dataset provides {dataset.view_types}"
        )

    storage_factory = app_context.injector.get(DatasetStorageFactoryPort)
    storage = await storage_factory.open(dataset.id, org_id=runtime_ctx.org_id)
    rows = await storage.list_samples(
        return_lazyframe=True,
        with_labels=runtime_ctx.sample_filter is not None,
        with_predictions=runtime_ctx.sample_filter is not None,
        sample_ids=runtime_ctx.sample_ids,
    )
    if runtime_ctx.sample_filter is not None:
        if dataset.dataset_type != "image_sc":
            raise ValueError("sample_filter is only supported for image_sc datasets")
        rows = parse_and_apply_workflow_sample_filter(
            cast(Any, rows), runtime_ctx.sample_filter
        )
    total_samples = int(cast(Any, rows).select(pl.len()).collect().item())

    repo = app_context.injector.get(PredictionRepository)
    existing_job = await repo.get_prediction_job(runtime_ctx.job_id, runtime_ctx.org_id)
    existing_summary = (
        existing_job.summary
        if existing_job is not None and isinstance(existing_job.summary, dict)
        else {}
    )
    summary: dict[str, Any] = {
        **existing_summary,
        "model_id": model.id,
        "dataset_id": dataset.id,
        "total_samples": total_samples,
        "successful": 0,
        "failed": 0,
        "processed": 0,
        "started_at": datetime.now(UTC).isoformat(),
        "model_version": runtime_ctx.model_version or f"model-{model.id[:8]}",
    }
    await repo.update_prediction_job_status(
        runtime_ctx.job_id, JobStatus.RUNNING, summary=summary
    )
    last_flush = time.monotonic()
    flush_rows = app_context.shared.config.sc.pipeline.prediction_progress_flush_rows
    flush_seconds = (
        app_context.shared.config.sc.pipeline.prediction_progress_flush_seconds
    )

    async def flush_progress(*, force: bool = False) -> None:
        nonlocal last_flush
        processed = int(summary["processed"])
        now = time.monotonic()
        if not (
            force or processed % flush_rows == 0 or now - last_flush >= flush_seconds
        ):
            return
        await repo.update_prediction_job_status(
            runtime_ctx.job_id,
            JobStatus.RUNNING,
            summary=dict(summary),
        )
        last_flush = now

    materializer = app_context.injector.get(ScInspectionMaterializerPort)
    async with AsyncExitStack() as exit_stack:
        materialization = await materializer.materialize(
            rows_lazyframe=rows,
            dataset_id=dataset.id,
            job_id=runtime_ctx.job_id,
            image_types=["patch_template", "patch_defective"],
            max_output_bytes=(
                app_context.shared.config.sc.pipeline.prediction_max_materialized_bytes
            ),
        )
        exit_stack.callback(materialization.cleanup)
        if materialization.errors:
            _runtime_logger().warning(
                "SC prediction materialization completed with %d image errors",
                len(materialization.errors),
            )

        labels: Sequence[str] | None = None
        if require_model_labels:
            raw_labels = model_metadata.get("label_space", [])
            if not isinstance(raw_labels, Sequence) or isinstance(
                raw_labels, (str, bytes)
            ):
                raise ValueError("YOLO model metadata must include label_space")
            labels = [str(label) for label in raw_labels]
            if not labels:
                raise ValueError("YOLO model metadata must include label_space")

        async def prediction_results():
            for prediction in _predict_rows(
                artifact_storage=app_context.shared.artifact_storage,
                model_uri=model.uri,
                materialization_manifest=materialization.manifest,
                kernel=kernel,
                label_space=labels,
            ):
                confidence_raw = prediction.get("confidence")
                confidence = (
                    float(confidence_raw)
                    if isinstance(confidence_raw, int | float)
                    else None
                )
                scores = prediction.get("scores")
                all_scores = (
                    {str(key): float(value) for key, value in scores.items()}
                    if isinstance(scores, dict)
                    else None
                )
                result = StoragePredictionResult(
                    sample_id=str(prediction.get("sample_id", "")),
                    predicted_label=str(prediction.get("label", "")),
                    confidence=confidence,
                    all_scores=all_scores,
                    model_id=model.id,
                    target=runtime_ctx.target,
                    model_version=str(summary["model_version"]),
                    job_id=runtime_ctx.job_id,
                    error=(
                        str(prediction["error"])
                        if prediction.get("error") is not None
                        else None
                    ),
                )
                summary["failed" if result.error else "successful"] += 1
                summary["processed"] += 1
                yield result
                await flush_progress()

        await storage.write_predictions(
            prediction_results(),
            job_id=runtime_ctx.job_id,
            model_id=model.id,
            model_version=str(summary["model_version"]),
            batch_size=(
                app_context.shared.config.sc.pipeline.prediction_write_batch_rows
            ),
        )

    publisher = app_context.shared.redis_event_publisher
    if publisher is not None:
        await publisher.publish_prediction_refresh(
            dataset_id=dataset.id,
            job_id=runtime_ctx.job_id,
        )
    summary["completed_at"] = datetime.now(UTC).isoformat()
    await flush_progress(force=True)
    await repo.update_prediction_job_status(
        runtime_ctx.job_id,
        JobStatus.COMPLETED,
        summary=summary,
    )
    await repo.add_prediction_event(
        PredictionEvent(
            job_id=runtime_ctx.job_id,
            ts=datetime.now(UTC),
            message="SC prediction completed",
            payload={"summary": summary},
        )
    )
    return summary


@SC_RUNTIME_ROUTER.predictor(
    id="resnet50-sc-v1",
    name="ResNet-50 SC Defect Prediction",
    input_view=SC_PATCH_IMAGE_V1,
    input_model=SC_RESNET_MODEL_V1,
    algo_id="resnet50-sc",
    algo_version="1",
    routes=_prediction_route(),
)
async def resnet_sc_predictor(ctx: PredictionRuntimeContext) -> dict[str, Any]:
    from ml_library import predict_resnet

    return await _run_sc_prediction(
        ctx,
        kernel=predict_resnet,
        require_model_labels=False,
    )


@SC_RUNTIME_ROUTER.predictor(
    id="yolo-sc-v1",
    name="YOLO SC Detection Prediction",
    input_view=SC_PATCH_IMAGE_V1,
    input_model=SC_YOLO_MODEL_V1,
    algo_id="yolo-sc",
    algo_version="1",
    routes=_prediction_route(),
)
async def yolo_sc_predictor(ctx: PredictionRuntimeContext) -> dict[str, Any]:
    from ml_library import predict_yolo

    return await _run_sc_prediction(
        ctx,
        kernel=predict_yolo,
        require_model_labels=True,
    )


__all__ = ["resnet_sc_predictor", "yolo_sc_predictor"]
