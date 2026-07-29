"""Prefect prediction flow — co-located in the API module.

Prediction dispatch goes through the executable predictor registry
(``get_predictor`` → ``Predictor`` Protocol).  Model loading is handled
by the predictor itself; this flow constructs ``PredictContext``,
``ModelRef``, and normalized sample payloads, then delegates execution.
"""

from __future__ import annotations
# pyright: reportMissingImports=false

import base64
import inspect
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from typing import Any, cast

import asyncstdlib as a
from prefect import flow, get_run_logger, task
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.runtime import (
    BatchPredictResult,
    DatasetRef,
    ModelRef,
    PredictContext,
)

from app.composition import build_flow_app_context, close_flow_app_context
from app.core.config import load_config
from app.modules.datasets.domain.sample_row import (
    PredictionResult as StoragePredictionResult,
)
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.types import catalog

from app.shared.context import AppContext
from app.shared.api.schemas import (
    Dataset,
    DatasetStorageMode,
    JobStatus,
    Model,
    PredictionEvent,
    TaskSpec,
)

from app.shared.db.models import (
    AnnotationORM,
    ArtifactORM,
    DatasetORM,
    PredictionEventORM,
    PredictionJobORM,
    SampleORM,
    TrainingJobORM,
)

PREDICTION_PROGRESS_FLUSH_EVERY = 50
PREDICTION_PROGRESS_FLUSH_INTERVAL_SECONDS = 1.0


def get_predictor(predictor_id: str) -> Any:
    """Lazy worker-boundary import kept patchable for flow tests."""

    from app.runtime_compat.ml.predictors import get_predictor as load_predictor

    return load_predictor(predictor_id)


def _dataset_storage_factory(ctx: AppContext) -> DatasetStorageFactoryPort:
    if ctx.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    return ctx.injector.get(DatasetStorageFactoryPort)


@dataclass
class PredictionRepository:
    session_factory: async_sessionmaker[AsyncSession]

    async def get_dataset(
        self, dataset_id: str, org_id: str | None = None
    ) -> Dataset | None:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id and not row.is_public:
                return None
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

    async def get_model(self, artifact_id: str, org_id: str) -> Model | None:
        async with self.session_factory() as session:
            stmt = (
                select(ArtifactORM, TrainingJobORM, DatasetORM)
                .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
                .join(DatasetORM, TrainingJobORM.dataset_id == DatasetORM.id)
                .where(ArtifactORM.id == artifact_id)
                .where(ArtifactORM.kind == "model")
                .where(
                    or_(
                        TrainingJobORM.org_id == org_id,
                        TrainingJobORM.is_public.is_(True),
                    )
                )
            )
            row = (await session.execute(stmt)).first()
            if row is None:
                return None
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

    async def get_prediction_job(
        self, job_id: str, org_id: str | None = None
    ) -> Any | None:
        async with self.session_factory() as session:
            row = await session.get(PredictionJobORM, job_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id:
                return None
            return row

    async def update_prediction_job_status(
        self, job_id: str, status: str, summary: dict[str, Any] | None = None
    ) -> None:
        async with self.session_factory() as session:
            row = await session.get(PredictionJobORM, job_id)
            if row is None:
                return
            row.status = status
            row.updated_at = datetime.now(timezone.utc)
            if summary is not None:
                row.summary_json = summary
            await session.commit()

    async def add_prediction_event(self, event: PredictionEvent) -> None:
        async with self.session_factory() as session:
            session.add(
                PredictionEventORM(
                    job_id=event.job_id,
                    ts=event.ts,
                    level=event.level,
                    message=event.message,
                    payload=event.payload,
                )
            )
            await session.commit()

    async def list_annotations_for_dataset(
        self, dataset_id: str
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = (
                select(AnnotationORM)
                .join(SampleORM, AnnotationORM.sample_id == SampleORM.id)
                .where(SampleORM.dataset_id == dataset_id)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "id": r.id,
                    "sample_id": r.sample_id,
                    "label": r.label,
                    "annotation_value": r.annotation_value,
                    "created_by": r.created_by,
                    "created_at": r.created_at,
                }
                for r in rows
            ]


# ── App context helpers (adapted from worker → API) ──────────────────────


async def _with_app_context() -> tuple[AppContext, bool]:
    cfg = load_config()
    return build_flow_app_context(cfg), True


def _prediction_repository(ctx: AppContext) -> PredictionRepository:
    return PredictionRepository(session_factory=ctx.shared.session_factory.sessionmaker)


async def _get_image_bytes(sample: Any, storage: Any) -> bytes | None:
    """Resolve the first image URI on *sample* to raw bytes.

    Works with :class:`Sample` and :class:`SampleRow` — both expose
    ``image_uris: list[str]``.
    """
    image_uris: list[str] = getattr(sample, "image_uris", None) or []
    if not image_uris:
        return None
    uri = image_uris[0]
    if uri.startswith("data:"):
        try:
            _, encoded = uri.split(",", 1)
            return base64.b64decode(encoded)
        except Exception:
            return None
    if uri.startswith("s3://") or uri.startswith("memory://"):
        try:
            return await storage.get_bytes(uri)
        except (FileNotFoundError, KeyError):
            return None
    return None


def _resolve_sparse_chunk_size(ctx: AppContext) -> int:
    """Resolve per-chunk batch size for sparse prediction from app config."""
    try:
        return int(ctx.shared.config.prediction.sparse_chunk_size)
    except (TypeError, ValueError, KeyError, AttributeError):
        return 32


# ── Helpers ───────────────────────────────────────────────────────────────


def _batch_result_to_dicts(
    result: BatchPredictResult,
) -> list[dict[str, Any]]:
    """Convert :class:`BatchPredictResult` to the legacy list-of-dicts format
    consumed by ``persist_chunk_results`` downstream."""
    dicts: list[dict[str, Any]] = []
    for pred in result.predictions:
        d: dict[str, Any] = {
            "sample_id": pred.sample_id,
            "label": pred.label,
            "confidence": pred.confidence,
            "scores": pred.scores,
        }
        error = pred.metadata.get("error") if pred.metadata else None
        if error:
            d["error"] = error
        dicts.append(d)
    return dicts


# ── Prefect tasks ─────────────────────────────────────────────────────────


@task(name="predict-chunk")
async def predict_chunk(
    job_id: str,
    model_id: str,
    org_id: str,
    target: str,
    prompt: str | None,
    sample_ids: list[str],
) -> list[dict[str, Any]]:
    logger = get_run_logger()
    logger.info(
        "predict_chunk started: job_id=%s model_id=%s sample_count=%d",
        job_id,
        model_id,
        len(sample_ids),
    )
    app_context, should_close = await _with_app_context()
    try:
        repo = _prediction_repository(app_context)
        model = await repo.get_model(model_id, org_id)
        if model is None:
            logger.error("Model not found for predict_chunk: %s", model_id)
            raise ValueError(f"Model not found: {model_id}")
        logger.info("predict_chunk: model loaded successfully model_id=%s", model_id)

        storage = app_context.shared.artifact_storage

        if model.dataset_id is None:
            raise ValueError(f"Model has no dataset: {model_id}")
        dataset_id = model.dataset_id
        dataset = await repo.get_dataset(dataset_id, org_id)
        if dataset is None:
            logger.error("predict_chunk: dataset not found dataset_id=%s", dataset_id)
            raise ValueError(f"Dataset not found: {dataset_id}")

        storage_agg = await _dataset_storage_factory(app_context).open(
            dataset_id,
            org_id=org_id,
        )
        samples_by_id = await storage_agg.get_samples_by_id(sample_ids)

        payload_samples: list[dict[str, Any]] = []
        for sample_id in sample_ids:
            row = samples_by_id.get(sample_id)
            if row is None:
                continue
            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            text_input = metadata.get("text")
            question_input = prompt or str(metadata.get("question", ""))

            image_bytes = await _get_image_bytes(row, storage)

            payload_samples.append(
                {
                    "sample_id": row.sample_id,
                    "image_bytes": image_bytes,
                    "metadata": metadata,
                    "image_uris": row.image_uris,
                    "question": question_input,
                    "text": text_input,
                }
            )

        if not payload_samples:
            logger.warning("predict_chunk: no valid payload samples, returning empty")
            return []

        trainer_id = model.trainer_id or model.trainer_name or ""
        if not trainer_id:
            logger.error(
                "predict_chunk: no predictor_id resolved from model %s", model.id
            )
            raise ValueError(f"No predictor_id resolved from model {model.id}")
        predictor_id = catalog.resolve_predictor_id(trainer_id)

        predictor_factory = get_predictor(predictor_id)
        predictor = cast(Any, predictor_factory(artifact_storage=storage))
        model_ref = ModelRef(
            uri=model.uri,
            format=model.format,
            metadata=model.metadata if isinstance(model.metadata, dict) else {},
        )
        predict_ctx = PredictContext(
            job_id=job_id,
            trainer_id=predictor_id,
            model_ref=model_ref,
            dataset_ref=DatasetRef(
                dataset_id=dataset.id,
                sample_ids=sample_ids,
                label_space=list(dataset.task_spec.label_space),
            ),
            target=target,
        )
        logger.info(
            "predict_chunk: loading model and running prediction predictor_id=%s sample_count=%d",
            predictor_id,
            len(payload_samples),
        )
        await predictor.load_model(model_ref)
        batch_result = await predictor.predict_batch(predict_ctx, payload_samples)
        result = _batch_result_to_dicts(batch_result)
        logger.info(
            "predict_chunk: prediction complete result_count=%d",
            len(result),
        )
        return result
    finally:
        if should_close:
            await close_flow_app_context(app_context)


@task(name="persist-chunk")
async def persist_chunk_results(
    job_id: str,
    model_id: str,
    org_id: str,
    target: str,
    model_version: str | None,
    sample_ids: list[str],
    worker_results: list[dict[str, Any]],
) -> dict[str, Any]:
    logger = get_run_logger()
    logger.info(
        "persist_chunk_results started: job_id=%s model_id=%s sample_count=%d result_count=%d",
        job_id,
        model_id,
        len(sample_ids),
        len(worker_results),
    )
    app_context, should_close = await _with_app_context()
    try:
        repo = _prediction_repository(app_context)
        model = await repo.get_model(model_id, org_id)
        if model is None:
            logger.error("persist_chunk_results: model not found model_id=%s", model_id)
            raise ValueError(f"Model not found: {model_id}")
        if model.dataset_id is None:
            raise ValueError(f"Model has no dataset: {model_id}")
        storage_agg = await _dataset_storage_factory(app_context).open(
            model.dataset_id,
            org_id=org_id,
        )
        outcome = await _persist_worker_results(
            repo=repo,
            storage_agg=storage_agg,
            job_id=job_id,
            model=model,
            target=target,
            model_version=model_version,
            sample_ids=sample_ids,
            worker_results=worker_results,
        )
        logger.info(
            "persist_chunk_results complete: successful=%d failed=%d processed=%d",
            outcome.get("successful", 0),
            outcome.get("failed", 0),
            outcome.get("processed", 0),
        )
        return outcome
    finally:
        if should_close:
            await close_flow_app_context(app_context)


async def _persist_worker_results(
    *,
    repo: PredictionRepository,
    storage_agg: Any,
    job_id: str,
    model: Model,
    target: str,
    model_version: str | None,
    sample_ids: list[str],
    worker_results: list[dict[str, Any]],
) -> dict[str, Any]:
    version_tag = model_version or f"model-{model.id[:8]}"
    worker_by_sample = {str(item.get("sample_id", "")): item for item in worker_results}
    successful = 0
    failed = 0
    predictions: list[dict[str, Any]] = []
    storage_results: list[StoragePredictionResult] = []
    samples_by_id = await storage_agg.get_samples_by_id(sample_ids)
    for sample_id in sample_ids:
        sample = samples_by_id.get(sample_id)
        if sample is None:
            failed += 1
            continue
        worker_result = worker_by_sample.get(
            sample.sample_id,
            {"sample_id": sample.sample_id, "error": "missing worker result"},
        )
        confidence_raw = worker_result.get("confidence")
        confidence = (
            float(confidence_raw) if isinstance(confidence_raw, int | float) else None
        )
        scores = worker_result.get("scores")
        all_scores = (
            {str(k): float(v) for k, v in scores.items()}
            if isinstance(scores, dict)
            else None
        )
        runtime_error = worker_result.get("error")
        result = StoragePredictionResult(
            sample_id=sample.sample_id,
            predicted_label=(str(worker_result.get("label", "")) or "embedding")
            if target == "embedding"
            else str(worker_result.get("label", "")),
            confidence=confidence,
            all_scores=all_scores,
            model_id=model.id,
            target=target,
            model_version=version_tag,
            job_id=job_id,
            error=str(runtime_error) if runtime_error else None,
        )
        storage_results.append(result)
        predictions.append(
            {
                "sample_id": result.sample_id,
                "predicted_label": result.predicted_label,
                "confidence": result.confidence,
                "all_scores": result.all_scores,
                "model_id": result.model_id,
                "target": result.target,
                "model_version": result.model_version,
                "job_id": result.job_id,
                "error": result.error,
            }
        )
        if result.error:
            failed += 1
        else:
            successful += 1

    async def result_stream():
        for result in storage_results:
            yield result

    await storage_agg.write_predictions(
        result_stream(),
        job_id=job_id,
        model_id=model.id,
        model_version=version_tag,
    )
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


# ── Public flow wrapper ────────────────────────────────────────────────────


async def _run_prediction_job_with_context(
    *,
    app_context: AppContext,
    job_id: str,
    dataset_id: str,
    model_id: str,
    org_id: str,
    target: str,
    model_version: str | None,
    sample_ids: list[str] | None,
    sample_filter: dict[str, Any] | None = None,
    prompt: str | None = None,
    requested_predictor_id: str | None = None,
) -> dict[str, Any]:
    logger = get_run_logger()
    repo = _prediction_repository(app_context)
    dataset = await repo.get_dataset(dataset_id, org_id)
    if dataset is None:
        raise ValueError(f"Dataset not found: {dataset_id}")

    # ── Resolve predictor's declared view_id ────────────────────────
    model = await repo.get_model(model_id, org_id)
    if model is None:
        raise ValueError(f"Model not found: {model_id}")

    trainer_id = model.trainer_id or model.trainer_name or ""
    if not trainer_id:
        raise ValueError(f"No predictor_id resolved from model {model.id}")
    predictor_id = catalog.resolve_predictor_id(
        trainer_id,
        requested_predictor_id=requested_predictor_id,
    )

    model_metadata = model.metadata if isinstance(model.metadata, dict) else {}
    predictor_metadata = catalog.validate_predictor_model_contract(
        predictor_id,
        model_contract=model_metadata.get("model_contract"),
        model_schema_version=model_metadata.get("model_schema_version"),
    )
    view_id = predictor_metadata.view_id
    view_metadata = catalog.get_view_meta(view_id)
    if view_id not in dataset.view_types:
        raise ValueError(
            f"Predictor {predictor_id!r} requires view {view_id!r}, "
            f"dataset provides {dataset.view_types}"
        )

    # ── Open dataset storage via factory ────────────────────────────
    storage_agg = await _dataset_storage_factory(app_context).open(
        dataset_id,
        org_id=org_id,
    )
    lf = await storage_agg.list_samples(
        return_lazyframe=True,
        with_labels=sample_filter is not None,
        with_predictions=sample_filter is not None,
        sample_ids=sample_ids,
    )
    if sample_filter is not None:
        if dataset.dataset_type != "image_sc":
            raise ValueError("sample_filter is only supported for image_sc datasets")
        from app.modules.sc.app.services.sample_filter import (
            parse_and_apply_workflow_sample_filter,
        )

        lf = parse_and_apply_workflow_sample_filter(cast(Any, lf), sample_filter)
    import polars as pl

    total_samples = int(cast(Any, lf).select(pl.len()).collect().item())
    logger.info(
        "Dataset loaded: %d rows for prediction, view=%s", total_samples, view_id
    )

    model_ref = ModelRef(
        uri=model.uri,
        format=model.format,
        metadata=model.metadata if isinstance(model.metadata, dict) else {},
    )
    ctx = PredictContext(
        job_id=job_id,
        trainer_id=predictor_id,
        model_ref=model_ref,
        dataset_ref=DatasetRef(
            dataset_id=dataset.id,
            label_space=list(dataset.task_spec.label_space),
        ),
        target=target,
    )

    predictor_fn = get_predictor(predictor_id)

    existing_job = await repo.get_prediction_job(job_id, org_id)
    existing_summary = (
        existing_job.summary_json
        if existing_job is not None and isinstance(existing_job.summary_json, dict)
        else {}
    )

    summary: dict[str, Any] = {
        **existing_summary,
        "model_id": model_id,
        "dataset_id": dataset_id,
        "total_samples": total_samples,
        "successful": 0,
        "failed": 0,
        "processed": 0,
        "started_at": datetime.now(UTC).isoformat(),
        "model_version": model_version or f"model-{model_id[:8]}",
    }
    await repo.update_prediction_job_status(job_id, JobStatus.RUNNING, summary=summary)
    last_progress_flush_at = time.monotonic()

    async def flush_prediction_progress(*, force: bool = False) -> None:
        nonlocal last_progress_flush_at
        processed = int(summary["processed"])
        now = time.monotonic()
        should_flush = (
            force
            or processed % PREDICTION_PROGRESS_FLUSH_EVERY == 0
            or now - last_progress_flush_at
            >= PREDICTION_PROGRESS_FLUSH_INTERVAL_SECONDS
        )
        if not should_flush:
            return
        await repo.update_prediction_job_status(
            job_id,
            JobStatus.RUNNING,
            summary=dict(summary),
        )
        last_progress_flush_at = now

    async def prediction_results(exit_stack: AsyncExitStack):
        materialization = None
        predictor_parameters = inspect.signature(predictor_fn).parameters
        supports_materialized_dataset = "materialized_dataset" in predictor_parameters
        if supports_materialized_dataset:
            materializers = catalog.capabilities.materializers_for(
                view_id,
                purpose="predict",
                storage_mode=dataset.storage_mode.value,
            )
            if len(materializers) != 1:
                raise RuntimeError(
                    f"Expected exactly one materializer for view={view_id!r}, "
                    f"purpose='predict', storage_mode="
                    f"{dataset.storage_mode.value!r}; found "
                    f"{[item.id for item in materializers]}"
                )
            materializer_metadata = materializers[0]
            if app_context.injector is None:
                raise RuntimeError("AppContext injector was not initialized")
            from app.runtime_compat.materializers import (
                resolve_local_materializer,
            )

            materializer = resolve_local_materializer(
                app_context.injector,
                materializer_metadata.id,
            )
            materialization = await materializer.materialize(
                rows_lazyframe=lf,
                dataset_id=dataset_id,
                job_id=job_id,
                image_types=list(view_metadata.image_roles),
            )
            exit_stack.callback(materialization.cleanup)
            if materialization.errors:
                logger.warning(
                    "Materialization completed with %d image errors",
                    len(materialization.errors),
                )
        predictor_kwargs: dict[str, Any] = {
            "artifact_storage": app_context.shared.artifact_storage,
            "ctx": ctx,
            "model_ref": model_ref,
        }
        if "lazyframe" in predictor_parameters:
            predictor_kwargs["lazyframe"] = lf
        if materialization is not None and supports_materialized_dataset:
            predictor_kwargs["materialized_dataset"] = materialization.dataset
        predictions = predictor_fn(**predictor_kwargs)
        if inspect.isawaitable(predictions):
            predictions = await predictions
        async with a.scoped_iter(predictions) as prediction_iter:
            async for pred in prediction_iter:
                sample_id = str(pred.get("sample_id", ""))
                confidence_raw = pred.get("confidence")
                confidence = (
                    float(confidence_raw)
                    if isinstance(confidence_raw, int | float)
                    else None
                )
                scores = pred.get("scores")
                all_scores = (
                    {str(k): float(v) for k, v in scores.items()}
                    if isinstance(scores, dict)
                    else None
                )
                result = StoragePredictionResult(
                    sample_id=sample_id,
                    predicted_label=str(pred.get("label", "")),
                    confidence=confidence,
                    all_scores=all_scores,
                    model_id=model.id,
                    target=target,
                    model_version=summary["model_version"],
                    job_id=job_id,
                    error=pred.get("error"),
                )
                if result.error:
                    summary["failed"] += 1
                    logger.warning(
                        "prediction failed for sample %s: %s",
                        sample_id,
                        result.error,
                    )
                else:
                    summary["successful"] += 1
                summary["processed"] += 1
                if summary["processed"] % 50 == 0:
                    logger.info(
                        "prediction progress: %d/%d (ok=%d fail=%d)",
                        summary["processed"],
                        summary["total_samples"],
                        summary["successful"],
                        summary["failed"],
                    )
                yield result
                await flush_prediction_progress()

    async with AsyncExitStack() as exit_stack:
        await storage_agg.write_predictions(
            prediction_results(exit_stack),
            job_id=job_id,
            model_id=model.id,
            model_version=summary["model_version"],
        )
    event_publisher = app_context.shared.redis_event_publisher
    if event_publisher is not None:
        await event_publisher.publish_prediction_refresh(
            dataset_id=dataset_id, job_id=job_id
        )

    summary["completed_at"] = datetime.now(UTC).isoformat()
    await flush_prediction_progress(force=True)
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


@flow(name="prediction-predict-job")
async def predict_job_flow(
    job_id: str,
    dataset_id: str,
    model_id: str,
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
    import app.registrations  # noqa: F401  # trigger all mapper registrations

    logger = get_run_logger()
    logger.info(
        "Starting prediction-predict-job: job_id=%s dataset_id=%s model_id=%s org_id=%s target=%s created_by=%s",
        job_id,
        dataset_id,
        model_id,
        org_id,
        target,
        created_by,
    )
    if catalog_id is None or predictor_id is None or predictor_id != catalog_id:
        raise ValueError(
            "Prediction flow requires matching predictor_id and routed catalog_id"
        )
    if owner != "local_compat":
        raise ValueError("API-local prediction flow requires owner='local_compat'")
    route_metadata = catalog.get_predictor_meta(predictor_id)
    if input_contract != route_metadata.input_view.contract:
        raise ValueError(
            f"Prediction route input_contract={input_contract!r} does not match "
            f"predictor view contract={route_metadata.input_view.contract!r}"
        )
    logger.info(
        "Prediction runtime route: catalog=%s input=%s output=%s profile=%s "
        "algo=%s@%s code=%s missing_image_policy=%s",
        catalog_id,
        input_contract,
        output_contract,
        resource_profile,
        algo_id,
        algo_version,
        code_version,
        missing_image_policy,
    )
    app_context, should_close = await _with_app_context()
    try:
        result = await _run_prediction_job_with_context(
            app_context=app_context,
            job_id=job_id,
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
    finally:
        if should_close:
            await close_flow_app_context(app_context)
    if result.get("status") == "failed":
        logger.error(
            "Prediction job %s failed: %s | full result: %s",
            job_id,
            result.get("error"),
            result,
        )
    else:
        logger.info(
            "Prediction complete: total=%s successful=%s failed=%s",
            result.get("total_samples"),
            result.get("successful"),
            result.get("failed"),
        )
    return result


predict_job = predict_job_flow


__all__ = [
    "persist_chunk_results",
    "predict_chunk",
    "predict_job",
    "predict_job_flow",
]
