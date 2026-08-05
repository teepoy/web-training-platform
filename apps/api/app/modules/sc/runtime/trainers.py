from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from contextlib import AsyncExitStack
from typing import Any, cast

from prefect import get_run_logger

from app.core.registry import resolve_view_types
from app.modules.runtime.domain.context import TrainingRuntimeContext
from app.modules.runtime.domain.executables import (
    RuntimeOperation,
    RuntimeRouteDefinition,
)
from app.modules.sc.app.services.sample_filter import (
    parse_and_apply_workflow_sample_filter,
)
from app.modules.sc.app.services.training_images import image_bytes_are_readable
from app.modules.sc.app.services.training_selection import (
    limit_sc_training_rows_per_class,
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
from app.shared.db.models.artifacts import ArtifactORM
from app.shared.db.models.datasets import DatasetORM
from app.shared.domain.data_plane import DataPlaneManifest

logger = logging.getLogger(__name__)


def _runtime_logger() -> Any:
    try:
        return get_run_logger()
    except Exception:
        return logger


def _training_routes() -> tuple[RuntimeRouteDefinition, ...]:
    return (
        RuntimeRouteDefinition(
            operation=RuntimeOperation.TRAIN,
            deployment="train-job-deployment",
            resource_profile="gpu",
            owner="local_compat",
            missing_image_policy="fail",
            output_contract="trainer_model",
        ),
        RuntimeRouteDefinition(
            operation=RuntimeOperation.TRAIN_AND_PREDICT,
            deployment="train-and-predict-deployment",
            resource_profile="gpu",
            owner="local_compat",
            missing_image_policy="skip",
            output_contract="sample.predictions.v1",
        ),
    )


def _training_samples(
    manifest: DataPlaneManifest,
    *,
    missing_image_policy: str,
) -> list[Any]:
    from ml_library import TrainingSample
    from ml_library.data_loading import collect_parquet_dataset

    samples: list[Any] = []
    dataset = collect_parquet_dataset(parquet_paths_from_manifest(manifest))
    for row in dataset:
        label_value = row.get("label")
        label = str(label_value) if label_value is not None else ""
        if not label:
            continue
        defective = row.get("patch_defective_bytes")
        reference = row.get("patch_template_bytes")
        missing_roles = []
        if not image_bytes_are_readable(defective):
            missing_roles.append("patch_defective")
        if not image_bytes_are_readable(reference):
            missing_roles.append("patch_template")
        if missing_roles:
            if missing_image_policy == "skip":
                continue
            raise ValueError(
                "SC training image validation failed for "
                f"sample_id={row.get('sample_id', '')!r}: "
                f"missing or unreadable roles={missing_roles}"
            )
        samples.append(
            TrainingSample(
                sample_id=str(row.get("sample_id", "")),
                defective_image=cast(bytes, defective),
                reference_image=cast(bytes, reference),
                label=label,
            )
        )
    return samples


async def _train_kernel(
    *,
    runtime_ctx: TrainingRuntimeContext,
    label_space: list[str],
    artifact_storage: Any,
    materialization_manifest: DataPlaneManifest,
    kernel: Callable[..., Any],
    missing_image_policy: str,
) -> dict[str, Any]:
    samples = _training_samples(
        materialization_manifest,
        missing_image_policy=missing_image_policy,
    )
    output = kernel(samples, label_space)
    checkpoint_object = f"models/{runtime_ctx.job_id}/checkpoint.pt"
    metrics_object = f"models/{runtime_ctx.job_id}/metrics.json"
    model_uri = await artifact_storage.put_bytes(
        object_name=checkpoint_object,
        data=output.checkpoint,
        content_type="application/octet-stream",
    )
    metrics_uri = await artifact_storage.put_bytes(
        object_name=metrics_object,
        data=json.dumps(output.metrics, sort_keys=True).encode("utf-8"),
        content_type="application/json",
    )
    return {
        "model_uri": model_uri,
        "metrics": dict(output.metrics),
        "artifact_uris": [model_uri, metrics_uri],
        "metadata": dict(output.metadata),
    }


def _trained_model_metadata(
    *,
    runtime_ctx: TrainingRuntimeContext,
    label_space: list[str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    from app.modules.runtime.catalog import runtime_catalog

    trainer = runtime_catalog.get_trainer_meta(runtime_ctx.trainer_id)
    runtime_labels = metadata.get("label_space")
    if not isinstance(runtime_labels, list):
        runtime_labels = label_space
    return {
        **metadata,
        "trainer_id": runtime_ctx.trainer_id,
        "model_contract": trainer.output_model.contract,
        "model_schema_version": trainer.output_model.schema_version,
        "predictor_ids": list(trainer.predictor_ids),
        "label_space": runtime_labels,
        "source_dataset_id": runtime_ctx.dataset_id,
    }


async def _run_sc_training(
    runtime_ctx: TrainingRuntimeContext,
    *,
    kernel: Callable[..., Any],
) -> dict[str, Any]:
    import app.registrations  # noqa: F401
    import polars as pl

    app_context = runtime_ctx.app_context
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    if runtime_ctx.missing_image_policy not in {"fail", "skip"}:
        raise ValueError("SC training requires missing_image_policy='fail' or 'skip'")

    async with app_context.shared.session_factory() as session:
        dataset_row = await session.get(DatasetORM, runtime_ctx.dataset_id)
        if dataset_row is None:
            raise ValueError(f"Dataset not found: {runtime_ctx.dataset_id}")
        dataset_type = dataset_row.dataset_type
        dataset_org_id = dataset_row.org_id
        dataset_meta = (
            dict(dataset_row.dataset_meta)
            if isinstance(dataset_row.dataset_meta, dict)
            else {}
        )
    if dataset_type != "image_sc":
        raise ValueError(
            f"SC trainer {runtime_ctx.trainer_id!r} requires image_sc dataset"
        )
    if SC_PATCH_IMAGE_V1.view_id not in resolve_view_types(dataset_type):
        raise ValueError(
            f"Dataset type {dataset_type!r} does not provide "
            f"{SC_PATCH_IMAGE_V1.view_id!r}"
        )

    storage_factory = app_context.injector.get(DatasetStorageFactoryPort)
    storage = await storage_factory.open(
        runtime_ctx.dataset_id,
        org_id=dataset_org_id,
    )
    rows = await storage.list_samples(
        with_labels=True,
        with_predictions=runtime_ctx.sample_filter is not None,
        return_lazyframe=True,
        sample_ids=runtime_ctx.sample_ids,
    )
    if runtime_ctx.sample_filter is not None:
        rows = parse_and_apply_workflow_sample_filter(
            cast(Any, rows), runtime_ctx.sample_filter
        )
    rows = limit_sc_training_rows_per_class(rows)
    selected_rows = int(
        (await rows.select(pl.len().alias("rows")).collect_async()).item(0, "rows")
    )
    max_rows = app_context.shared.config.sc.pipeline.training_max_rows
    if selected_rows > max_rows:
        raise ValueError(
            f"SC training selection exceeds configured row budget: "
            f"{selected_rows} > {max_rows}"
        )

    materializer = app_context.injector.get(ScInspectionMaterializerPort)
    _runtime_logger().info(
        "SC trainer materializing input: trainer=%s rows=%d",
        runtime_ctx.trainer_id,
        selected_rows,
    )
    async with AsyncExitStack() as exit_stack:
        materialization = await materializer.materialize(
            rows_lazyframe=rows,
            dataset_id=runtime_ctx.dataset_id,
            job_id=runtime_ctx.job_id,
            image_types=["patch_template", "patch_defective"],
            max_output_bytes=(
                app_context.shared.config.sc.pipeline.training_max_materialized_bytes
            ),
        )
        exit_stack.callback(materialization.cleanup)
        if materialization.errors and runtime_ctx.missing_image_policy != "skip":
            raise ValueError(
                f"SC training materialization failed for "
                f"{len(materialization.errors)} image(s); first error: "
                f"{materialization.errors[0]}"
            )
        train_result = await _train_kernel(
            runtime_ctx=runtime_ctx,
            label_space=list(dataset_meta.get("label_space", [])),
            artifact_storage=app_context.shared.artifact_storage,
            materialization_manifest=materialization.manifest,
            kernel=kernel,
            missing_image_policy=runtime_ctx.missing_image_policy,
        )

    artifacts: list[dict[str, Any]] = [
        {
            "uri": train_result["model_uri"],
            "kind": "model",
            "metadata": _trained_model_metadata(
                runtime_ctx=runtime_ctx,
                label_space=list(dataset_meta.get("label_space", [])),
                metadata=cast(dict[str, Any], train_result["metadata"]),
            ),
        }
    ]
    artifacts.extend(
        {"uri": uri, "kind": "metrics", "metadata": {}}
        for uri in cast(list[str], train_result["artifact_uris"])
        if uri and uri != train_result["model_uri"]
    )
    async with app_context.shared.session_factory() as session:
        for artifact in artifacts:
            if not artifact["uri"]:
                continue
            session.add(
                ArtifactORM(
                    id=str(uuid.uuid4()),
                    job_id=runtime_ctx.job_id,
                    uri=str(artifact["uri"]),
                    kind=str(artifact["kind"]),
                    metadata_json=cast(dict[str, Any], artifact["metadata"]),
                )
            )
        await session.commit()
    return {
        "job_id": runtime_ctx.job_id,
        "status": "completed",
        "artifacts": [item for item in artifacts if item["uri"]],
        "metrics": train_result["metrics"],
    }


@SC_RUNTIME_ROUTER.trainer(
    id="resnet50-sc-v1",
    name="ResNet-50 SC Defect Classifier",
    input_view=SC_PATCH_IMAGE_V1,
    output_model=SC_RESNET_MODEL_V1,
    predictor_ids=("resnet50-sc-v1",),
    algo_id="resnet50-sc",
    algo_version="1",
    routes=_training_routes(),
)
async def resnet_sc_train(ctx: TrainingRuntimeContext) -> dict[str, Any]:
    from ml_library import train_resnet

    return await _run_sc_training(ctx, kernel=train_resnet)


@SC_RUNTIME_ROUTER.trainer(
    id="yolo-sc-v1",
    name="YOLO SC Detection Trainer",
    input_view=SC_PATCH_IMAGE_V1,
    output_model=SC_YOLO_MODEL_V1,
    predictor_ids=("yolo-sc-v1",),
    algo_id="yolo-sc",
    algo_version="1",
    routes=_training_routes(),
)
async def yolo_sc_train(ctx: TrainingRuntimeContext) -> dict[str, Any]:
    from ml_library import train_yolo

    return await _run_sc_training(ctx, kernel=train_yolo)


__all__ = ["resnet_sc_train", "yolo_sc_train"]
