from __future__ import annotations

from typing import Any

from prefect import flow, get_run_logger

from app.composition import build_flow_app_context, close_flow_app_context
from app.core.config import load_config
from app.modules.runtime.catalog import runtime_catalog
from app.modules.runtime.domain.context import PredictionRuntimeContext
from app.modules.runtime.domain.events import collect_runtime_events
from app.shared.context import AppContext


async def execute_prediction_runtime(
    *,
    job_id: str,
    dataset_id: str | None,
    model_id: str,
    org_id: str,
    predictor_id: str,
    created_by: str,
    target: str,
    model_version: str | None = None,
    sample_ids: list[str] | None = None,
    sample_filter: dict[str, Any] | None = None,
    prompt: str | None = None,
    collection_id: str | None = None,
    collection_revision_id: str | None = None,
    app_context: AppContext | None = None,
) -> object:
    owns_context = app_context is None
    if app_context is None:
        app_context = build_flow_app_context(load_config(skip_runtime_validation=True))
    try:
        return await collect_runtime_events(
            runtime_catalog.stream_predict(
                predictor_id,
                PredictionRuntimeContext(
                    app_context=app_context,
                    job_id=job_id,
                    dataset_id=dataset_id,
                    model_id=model_id,
                    org_id=org_id,
                    predictor_id=predictor_id,
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
        if owns_context:
            await close_flow_app_context(app_context)


@flow(name="prediction-predict-job")
async def predict_job_flow(
    job_id: str,
    dataset_id: str | None,
    model_id: str,
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
    registration = runtime_catalog.get_predictor(predictor_id)
    get_run_logger().info(
        "Invoking registered predictor %s algo=%s@%s",
        predictor_id,
        registration.algo_id,
        registration.algo_version,
    )
    return await execute_prediction_runtime(
        job_id=job_id,
        dataset_id=dataset_id,
        model_id=model_id,
        org_id=org_id,
        predictor_id=predictor_id,
        created_by=created_by,
        target=target,
        model_version=model_version,
        sample_ids=sample_ids,
        sample_filter=sample_filter,
        prompt=prompt,
        collection_id=collection_id,
        collection_revision_id=collection_revision_id,
    )


predict_job = predict_job_flow

__all__ = ["execute_prediction_runtime", "predict_job", "predict_job_flow"]
