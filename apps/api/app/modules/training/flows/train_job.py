from __future__ import annotations

from typing import Any

from prefect import flow, get_run_logger

from app.composition import build_flow_app_context, close_flow_app_context
from app.core.config import load_config
from app.modules.runtime.catalog import runtime_catalog
from app.modules.runtime.domain.context import TrainingRuntimeContext
from app.modules.runtime.domain.events import collect_runtime_events
from app.shared.context import AppContext


async def execute_training_runtime(
    *,
    job_id: str,
    dataset_id: str | None,
    trainer_id: str,
    created_by: str,
    sample_ids: list[str] | None = None,
    sample_filter: dict[str, Any] | None = None,
    org_id: str = "",
    collection_id: str | None = None,
    collection_revision_id: str | None = None,
    app_context: AppContext | None = None,
) -> object:
    owns_context = app_context is None
    if app_context is None:
        app_context = build_flow_app_context(load_config(skip_runtime_validation=True))
    try:
        return await collect_runtime_events(
            runtime_catalog.stream_train(
                trainer_id,
                TrainingRuntimeContext(
                    app_context=app_context,
                    job_id=job_id,
                    dataset_id=dataset_id,
                    trainer_id=trainer_id,
                    created_by=created_by,
                    sample_ids=sample_ids,
                    sample_filter=sample_filter,
                    org_id=org_id,
                    collection_id=collection_id,
                    collection_revision_id=collection_revision_id,
                ),
            )
        )
    finally:
        if owns_context:
            await close_flow_app_context(app_context)


@flow(name="training-train-job")
async def train_job_flow(
    job_id: str,
    dataset_id: str | None,
    trainer_id: str,
    created_by: str = "system",
    org_id: str = "",
    collection_id: str | None = None,
    collection_revision_id: str | None = None,
) -> object:
    registration = runtime_catalog.get_trainer(trainer_id)
    get_run_logger().info(
        "Invoking registered trainer %s algo=%s@%s",
        trainer_id,
        registration.algo_id,
        registration.algo_version,
    )
    return await execute_training_runtime(
        job_id=job_id,
        dataset_id=dataset_id,
        trainer_id=trainer_id,
        created_by=created_by,
        org_id=org_id,
        collection_id=collection_id,
        collection_revision_id=collection_revision_id,
    )


__all__ = ["execute_training_runtime", "train_job_flow"]
