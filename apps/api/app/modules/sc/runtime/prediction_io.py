from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from sqlalchemy import or_, select

from app.modules.datasets.domain.sample_row import PredictionResult
from app.modules.runtime.domain.context import PredictionRuntimeContext
from app.modules.sc.runtime.data_source import (
    ScRuntimeSource,
    decode_collection_row_key,
)
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.api.schemas import Model
from app.shared.db.models import ArtifactORM, DatasetORM, TrainingJobORM
from app.shared.db.models.dataset_collections import DatasetCollectionORM


async def load_sc_prediction_model(ctx: PredictionRuntimeContext) -> Model:
    async with ctx.app_context.shared.session_factory() as session:
        stmt = (
            select(
                ArtifactORM,
                TrainingJobORM,
                DatasetORM,
                DatasetCollectionORM,
            )
            .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
            .outerjoin(DatasetORM, TrainingJobORM.dataset_id == DatasetORM.id)
            .outerjoin(
                DatasetCollectionORM,
                TrainingJobORM.collection_id == DatasetCollectionORM.id,
            )
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
        artifact, job, dataset, collection = row
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
            dataset_name=dataset.name if dataset is not None else None,
            collection_id=job.collection_id,
            collection_revision_id=job.collection_revision_id,
            collection_name=collection.name if collection is not None else None,
            trainer_id=job.trainer_id,
            trainer_name=job.trainer_id,
        )


async def write_sc_predictions(
    *,
    runtime_ctx: PredictionRuntimeContext,
    source: ScRuntimeSource,
    predictions: AsyncIterator[PredictionResult],
    model_id: str,
    model_version: str,
    batch_size: int,
) -> None:
    app_context = runtime_ctx.app_context
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    storage_factory = app_context.injector.get(DatasetStorageFactoryPort)
    if source.dataset_id is not None:
        storage = await storage_factory.open(
            source.dataset_id,
            org_id=runtime_ctx.org_id,
        )
        await storage.write_predictions(
            predictions,
            job_id=runtime_ctx.job_id,
            model_id=model_id,
            model_version=model_version,
            batch_size=batch_size,
        )
        return
    await _write_collection_predictions(
        source=source,
        predictions=predictions,
        storage_factory=storage_factory,
        org_id=runtime_ctx.org_id,
        job_id=runtime_ctx.job_id,
        model_id=model_id,
        model_version=model_version,
        batch_size=batch_size,
    )


async def _write_collection_predictions(
    *,
    source: ScRuntimeSource,
    predictions: AsyncIterator[PredictionResult],
    storage_factory: DatasetStorageFactoryPort,
    org_id: str,
    job_id: str,
    model_id: str,
    model_version: str,
    batch_size: int,
) -> None:
    queues: dict[str, asyncio.Queue[PredictionResult | None]] = {
        dataset_id: asyncio.Queue(maxsize=max(1, batch_size))
        for dataset_id in source.source_dataset_ids
    }

    async def queued_predictions(
        queue: asyncio.Queue[PredictionResult | None],
    ) -> AsyncIterator[PredictionResult]:
        while True:
            item = await queue.get()
            if item is None:
                return
            yield item

    tasks: list[asyncio.Task[Any]] = []
    for dataset_id, queue in queues.items():
        storage = await storage_factory.open(dataset_id, org_id=org_id)
        tasks.append(
            asyncio.create_task(
                storage.write_predictions(
                    queued_predictions(queue),
                    job_id=job_id,
                    model_id=model_id,
                    model_version=model_version,
                    batch_size=batch_size,
                ),
                name=f"collection-predictions-{dataset_id}",
            )
        )

    async def put_or_raise(
        queue: asyncio.Queue[PredictionResult | None],
        item: PredictionResult | None,
    ) -> None:
        put_task = asyncio.create_task(queue.put(item))
        done, _ = await asyncio.wait(
            [put_task, *tasks],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if put_task in done:
            return
        put_task.cancel()
        for task in done:
            if task is put_task:
                continue
            error = task.exception()
            if error is not None:
                raise error
        raise RuntimeError(
            "Collection prediction writer stopped before input completed"
        )

    try:
        async for prediction in predictions:
            dataset_id, sample_id = decode_collection_row_key(
                prediction.sample_id,
                allowed_dataset_ids=source.source_dataset_ids,
            )
            await put_or_raise(
                queues[dataset_id],
                replace(prediction, sample_id=sample_id),
            )
        for queue in queues.values():
            await put_or_raise(queue, None)
        await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


__all__ = ["load_sc_prediction_model", "write_sc_predictions"]
