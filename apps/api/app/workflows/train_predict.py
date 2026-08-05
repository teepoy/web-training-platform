from __future__ import annotations

from typing import Any

from prefect import flow, get_run_logger

from app.composition import build_flow_app_context, close_flow_app_context
from app.core.config import load_config
from app.modules.runtime.catalog import runtime_catalog
from app.modules.runtime.domain.context import TrainAndPredictRuntimeContext
from app.modules.runtime.domain.executables import RuntimeOperation


@flow(name="training-train-and-predict")
async def train_and_predict_flow(
    job_id: str,
    dataset_id: str | None,
    trainer_id: str,
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
    collection_id: str | None = None,
    collection_revision_id: str | None = None,
) -> object:
    del output_contract
    if catalog_id != trainer_id:
        raise ValueError(
            "Train-and-predict flow requires catalog_id matching trainer_id"
        )
    if owner != "local_compat":
        raise ValueError(
            "API-local train-and-predict flow requires owner='local_compat'"
        )
    registration = runtime_catalog.get_trainer(trainer_id)
    if input_contract != registration.metadata.input_view.contract:
        raise ValueError("Train-and-predict input contract does not match registration")
    resolved_predictor_id = runtime_catalog.resolve_predictor_id(
        trainer_id,
        requested_predictor_id=predictor_id,
    )
    get_run_logger().info(
        "Invoking registered train-and-predict %s algo=%s@%s profile=%s code=%s",
        trainer_id,
        algo_id,
        algo_version,
        resource_profile,
        code_version,
    )
    app_context = build_flow_app_context(load_config(skip_runtime_validation=True))
    try:
        return await runtime_catalog.invoke(
            RuntimeOperation.TRAIN_AND_PREDICT,
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
                missing_image_policy=missing_image_policy,
                collection_id=collection_id,
                collection_revision_id=collection_revision_id,
            ),
        )
    finally:
        await close_flow_app_context(app_context)


__all__ = ["train_and_predict_flow"]
