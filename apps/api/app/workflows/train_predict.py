from __future__ import annotations

from typing import Any

from prefect import flow, get_run_logger

from app.composition import build_flow_app_context, close_flow_app_context
from app.core.config import load_config
from app.modules.runtime.catalog import runtime_catalog
from app.modules.runtime.domain.context import TrainAndPredictRuntimeContext
from app.modules.runtime.domain.events import collect_runtime_events
from app.modules.training.app.services.preflight import TrainingPreflightService


@flow(name="training-train-and-predict")
async def train_and_predict_flow(
    job_id: str,
    dataset_id: str | None,
    trainer_id: str,
    org_id: str,
    predictor_id: str,
    created_by: str = "system",
    target: str = "image_classification",
    model_version: str | None = None,
    sample_ids: list[str] | None = None,
    sample_filter: dict[str, Any] | None = None,
    prompt: str | None = None,
    collection_id: str | None = None,
    collection_revision_id: str | None = None,
) -> object:
    registration = runtime_catalog.get_trainer(trainer_id)
    resolved_predictor_id = runtime_catalog.resolve_predictor_id(
        trainer_id,
        requested_predictor_id=predictor_id,
    )
    get_run_logger().info(
        "Invoking registered train-and-predict %s algo=%s@%s",
        trainer_id,
        registration.algo_id,
        registration.algo_version,
    )
    app_context = build_flow_app_context(load_config(skip_runtime_validation=True))
    try:
        if app_context.injector is None:
            raise RuntimeError("AppContext injector was not initialized")
        await app_context.injector.get(TrainingPreflightService).ensure_ready(
            dataset_id=dataset_id,
            collection_id=collection_id,
            collection_revision_id=collection_revision_id,
            org_id=org_id,
            sample_ids=sample_ids,
            sample_filter=sample_filter,
        )
        return await collect_runtime_events(
            runtime_catalog.stream_train_and_predict(
                trainer_id,
                TrainAndPredictRuntimeContext(
                    app_context=app_context,
                    job_id=job_id,
                    dataset_id=dataset_id,
                    trainer_id=trainer_id,
                    predictor_id=resolved_predictor_id,
                    org_id=org_id,
                    created_by=created_by,
                    target=target,
                    model_version=model_version,
                    sample_ids=sample_ids,
                    sample_filter=sample_filter,
                    prompt=prompt,
                    collection_id=collection_id,
                    collection_revision_id=collection_revision_id,
                ),
            )
        )
    finally:
        await close_flow_app_context(app_context)


__all__ = ["train_and_predict_flow"]
