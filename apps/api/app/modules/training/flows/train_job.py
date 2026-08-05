from __future__ import annotations

from typing import Any

from prefect import flow, get_run_logger

from app.composition import build_flow_app_context, close_flow_app_context
from app.core.config import load_config
from app.modules.runtime.catalog import runtime_catalog
from app.modules.runtime.domain.context import TrainingRuntimeContext
from app.modules.runtime.domain.executables import RuntimeOperation
from app.shared.context import AppContext


async def execute_training_runtime(
    *,
    job_id: str,
    dataset_id: str,
    trainer_id: str,
    created_by: str,
    sample_ids: list[str] | None = None,
    sample_filter: dict[str, Any] | None = None,
    missing_image_policy: str | None = None,
    app_context: AppContext | None = None,
) -> object:
    owns_context = app_context is None
    if app_context is None:
        app_context = build_flow_app_context(load_config(skip_runtime_validation=True))
    try:
        return await runtime_catalog.invoke(
            RuntimeOperation.TRAIN,
            trainer_id,
            TrainingRuntimeContext(
                app_context=app_context,
                job_id=job_id,
                dataset_id=dataset_id,
                trainer_id=trainer_id,
                created_by=created_by,
                sample_ids=sample_ids,
                sample_filter=sample_filter,
                missing_image_policy=missing_image_policy,
            ),
        )
    finally:
        if owns_context:
            await close_flow_app_context(app_context)


@flow(name="training-train-job")
async def train_job_flow(
    job_id: str,
    dataset_id: str,
    trainer_id: str,
    created_by: str = "system",
    catalog_id: str | None = None,
    input_contract: str | None = None,
    output_contract: str | None = None,
    resource_profile: str | None = None,
    owner: str | None = None,
    algo_id: str | None = None,
    algo_version: str | None = None,
    code_version: str | None = None,
    missing_image_policy: str | None = None,
) -> object:
    if catalog_id != trainer_id:
        raise ValueError("Training flow requires catalog_id matching trainer_id")
    if owner != "local_compat":
        raise ValueError("API-local training flow requires owner='local_compat'")
    registration = runtime_catalog.get_trainer(trainer_id)
    if input_contract != registration.metadata.input_view.contract:
        raise ValueError("Training input contract does not match registration")
    if output_contract != registration.metadata.output_model.contract:
        raise ValueError("Training output contract does not match registration")
    get_run_logger().info(
        "Invoking registered trainer %s algo=%s@%s profile=%s code=%s",
        trainer_id,
        algo_id,
        algo_version,
        resource_profile,
        code_version,
    )
    return await execute_training_runtime(
        job_id=job_id,
        dataset_id=dataset_id,
        trainer_id=trainer_id,
        created_by=created_by,
        missing_image_policy=missing_image_policy,
    )


__all__ = ["execute_training_runtime", "train_job_flow"]
