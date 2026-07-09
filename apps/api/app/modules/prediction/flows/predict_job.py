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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from typing import Any, cast

import asyncstdlib as a
from prefect import flow, get_run_logger, task
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_runtime.contracts import (
    BatchPredictResult,
    DatasetRef,
    ModelRef,
    PredictContext,
)

from app.composition import AppContainer, build_flow_container
from app.core.config import load_config
from app.modules.datasets.domain.sample_row import (
    PredictionResult as StoragePredictionResult,
)
from app.modules.prediction.flows._predictors import get_predictor

from app.shared.api.schemas import (
    Dataset,
    DatasetStorageMode,
    JobStatus,
    Model,
    PredictionEvent,
    SampleFeature,
    TaskSpec,
)

from app.shared.db.models import (
    AnnotationORM,
    ArtifactORM,
    DatasetORM,
    PredictionEventORM,
    PredictionJobORM,
    SampleFeatureORM,
    SampleORM,
    TrainingJobORM,
)
from app.shared.db.sql_repository import SqlRepository
from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.shared.infrastructure.redis.event_publisher import RedisEventPublisher

PREDICTION_PROGRESS_FLUSH_EVERY = 50
PREDICTION_PROGRESS_FLUSH_INTERVAL_SECONDS = 1.0


@asynccontextmanager
async def _flow_redis_event_publisher(
    container: AppContainer,
) -> AsyncIterator[RedisEventPublisher]:
    import redis.asyncio as redis_client  # type: ignore[import-untyped]

    cfg = container.config
    redis = redis_client.Redis(
        host=str(cfg.redis.host),
        port=int(cfg.redis.port),
        password=str(cfg.redis.password) if cfg.redis.password else None,
        db=int(cfg.redis.db),
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        await redis.ping()  # type: ignore[awaitable]
        yield RedisEventPublisher(cast(Any, redis))
    except Exception:
        yield RedisEventPublisher(None)
    finally:
        await redis.aclose()


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

    async def get_sample_feature(self, sample_id: str) -> SampleFeature | None:
        async with self.session_factory() as session:
            row = await session.get(SampleFeatureORM, sample_id)
            if row is None:
                return None
            return SampleFeature(
                sample_id=row.sample_id,
                embedding=row.embedding,
                embed_model=row.embed_model,
                computed_at=row.computed_at,
            )

    async def upsert_sample_feature(
        self, sample_id: str, embedding: list[float], embed_model: str
    ) -> SampleFeature:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            row = await session.get(SampleFeatureORM, sample_id)
            if row is None:
                row = SampleFeatureORM(
                    sample_id=sample_id,
                    embedding=embedding,
                    embed_model=embed_model,
                    computed_at=now,
                )
                session.add(row)
            else:
                row.embedding = embedding
                row.embed_model = embed_model
                row.computed_at = now
            await session.commit()
            try:
                dialect_name = session.bind.dialect.name
            except Exception:
                dialect_name = ""
            if dialect_name == "postgresql":
                await session.execute(
                    text(
                        "UPDATE sample_features SET embedding_vec = :vec::vector WHERE sample_id = :sid"
                    ),
                    {"vec": str(embedding), "sid": sample_id},
                )
                await session.commit()
        return SampleFeature(
            sample_id=sample_id,
            embedding=embedding,
            embed_model=embed_model,
            computed_at=now,
        )

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


# ── Container helpers (adapted from worker → API) ────────────────────────


async def _with_app_container() -> tuple[AppContainer, bool]:
    cfg = load_config()
    return build_flow_container(cfg), True


def _prediction_repository(container: AppContainer) -> PredictionRepository:
    return PredictionRepository(session_factory=container.session_factory)


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


def _resolve_sparse_chunk_size(container: AppContainer) -> int:
    """Resolve per-chunk batch size for sparse prediction from container config."""
    try:
        cfg = container.config
        if isinstance(cfg, dict):
            return int(cfg.get("prediction", {}).get("sparse_chunk_size", 32))
        return int(cfg.get("prediction", {}).get("sparse_chunk_size", 32))
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
    container, should_close = await _with_app_container()
    try:
        repo = _prediction_repository(container)
        model = await repo.get_model(model_id, org_id)
        if model is None:
            logger.error("Model not found for predict_chunk: %s", model_id)
            raise ValueError(f"Model not found: {model_id}")
        logger.info("predict_chunk: model loaded successfully model_id=%s", model_id)

        sql_repo = SqlRepository(session_factory=container.session_factory)
        storage = container.artifact_storage

        first_sample = await sql_repo.get_sample(sample_ids[0])
        if first_sample is None:
            logger.warning("predict_chunk: first sample not found, returning empty")
            return []
        dataset_id = first_sample.dataset_id
        dataset = await repo.get_dataset(dataset_id, org_id)
        if dataset is None:
            logger.error("predict_chunk: dataset not found dataset_id=%s", dataset_id)
            raise ValueError(f"Dataset not found: {dataset_id}")

        factory = DatasetStorageFactory(
            repo=sql_repo,
            storage=storage,
            payload_store=container.dataset_payload_store,
            ls_client=container.label_studio_client,
            session_factory=container.session_factory,
        )
        storage_agg = await factory.open(dataset_id, org_id=org_id)
        rows = await storage_agg.get_samples_batch(sample_ids)

        payload_samples: list[dict[str, Any]] = []
        for row in rows:
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

        predictor_id = model.trainer_id or model.trainer_name or ""
        if not predictor_id:
            logger.error(
                "predict_chunk: no predictor_id resolved from model %s", model.id
            )
            raise ValueError(f"No predictor_id resolved from model {model.id}")

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
            await container.close()


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
    container, should_close = await _with_app_container()
    try:
        repo = _prediction_repository(container)
        sql_repo = SqlRepository(session_factory=container.session_factory)
        model = await repo.get_model(model_id, org_id)
        if model is None:
            logger.error("persist_chunk_results: model not found model_id=%s", model_id)
            raise ValueError(f"Model not found: {model_id}")
        if model.dataset_id is None:
            raise ValueError(f"Model has no dataset: {model_id}")
        factory = DatasetStorageFactory(
            repo=sql_repo,
            storage=container.artifact_storage,
            payload_store=container.dataset_payload_store,
            ls_client=container.label_studio_client,
            session_factory=container.session_factory,
        )
        storage_agg = await factory.open(model.dataset_id, org_id=org_id)
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
            await container.close()


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
    samples = await storage_agg.get_samples_batch(sample_ids)
    for sample_id, sample in zip(sample_ids, samples, strict=True):
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


async def _run_prediction_job_with_container(
    *,
    container: AppContainer,
    job_id: str,
    dataset_id: str,
    model_id: str,
    org_id: str,
    target: str,
    model_version: str | None,
    sample_ids: list[str] | None,
    sample_filter: dict[str, Any] | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    logger = get_run_logger()
    repo = _prediction_repository(container)
    dataset = await repo.get_dataset(dataset_id, org_id)
    if dataset is None:
        raise ValueError(f"Dataset not found: {dataset_id}")

    # ── Resolve predictor's declared view_id ────────────────────────
    model = await repo.get_model(model_id, org_id)
    if model is None:
        raise ValueError(f"Model not found: {model_id}")

    predictor_id = model.trainer_id or model.trainer_name or ""
    if not predictor_id:
        raise ValueError(f"No predictor_id resolved from model {model.id}")

    try:
        predictor_factory = get_predictor(predictor_id)
        predictor_view_id: str | None = getattr(predictor_factory, "_view_id", None)
    except KeyError:
        predictor_view_id = None

    view_id = predictor_view_id or (
        dataset.view_types[0] if dataset.view_types else target
    )

    # ── Open dataset storage via factory ────────────────────────────
    factory = DatasetStorageFactory(
        repo=SqlRepository(session_factory=container.session_factory),
        storage=container.artifact_storage,
        payload_store=container.dataset_payload_store,
        ls_client=container.label_studio_client,
        session_factory=container.session_factory,
    )
    storage_agg = await factory.open(dataset_id, org_id=org_id)
    lf = await storage_agg.list_samples(
        return_lazyframe=True,
        with_labels=sample_filter is not None,
        with_predictions=sample_filter is not None,
        sample_ids=sample_ids,
    )
    if sample_filter is not None:
        if dataset.dataset_type != "image_sc":
            raise ValueError("sample_filter is only supported for image_sc datasets")
        from app.modules.sc.app.services.sc_plot_points_service import (
            apply_sc_workflow_sample_filter,
        )

        lf = apply_sc_workflow_sample_filter(cast(Any, lf), sample_filter)
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

    async def prediction_results():
        image_fetcher = None
        materialization = None
        supports_materialized_dataset = (
            "materialized_dataset" in inspect.signature(predictor_fn).parameters
        )
        if dataset.dataset_type == "image_sc":
            import os as _os_pj
            from app.modules.sc.adapter.grpc_image_fetcher import GrpcImageFetcher
            from app.modules.sc.app.services.inspection_materializer import (
                ScInspectionMaterializer,
            )

            image_fetcher = GrpcImageFetcher(
                addr=_os_pj.environ.get("IMAGE_PARSER_GRPC_ADDR", "image-parser:9092")
            )
            if supports_materialized_dataset:
                materializer = ScInspectionMaterializer(image_fetcher)
                materialization = await materializer.materialize(
                    rows_lazyframe=lf,
                    image_types=["patch_template", "patch_defective"],
                )
                if materialization.errors:
                    logger.warning(
                        "SC materialization completed with %d image errors",
                        len(materialization.errors),
                    )
        try:
            predictor_kwargs: dict[str, Any] = {
                "artifact_storage": container.artifact_storage,
                "ctx": ctx,
                "lazyframe": lf,
                "model_ref": model_ref,
            }
            if "image_fetcher" in inspect.signature(predictor_fn).parameters:
                predictor_kwargs["image_fetcher"] = image_fetcher
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
        finally:
            if materialization is not None:
                materialization.cleanup()
            if image_fetcher is not None:
                await image_fetcher.close()

    await storage_agg.write_predictions(
        prediction_results(),
        job_id=job_id,
        model_id=model.id,
        model_version=summary["model_version"],
    )
    async with _flow_redis_event_publisher(container) as event_publisher:
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
    container, should_close = await _with_app_container()
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
            sample_filter=sample_filter,
            prompt=prompt,
        )
    finally:
        if should_close:
            await container.close()
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
