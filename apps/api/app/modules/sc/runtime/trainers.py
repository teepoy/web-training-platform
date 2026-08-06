from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, cast

from prefect import get_run_logger

from app.modules.runtime.domain.context import TrainingRuntimeContext
from app.modules.runtime.domain.events import (
    ArtifactProduced,
    MetricsReported,
    OperationCompleted,
    RuntimeEventStream,
    RuntimeExecutionError,
    RuntimeIssueReported,
)
from app.modules.sc.app.services.sample_filter import (
    parse_and_apply_workflow_sample_filter,
)
from app.modules.sc.app.services.training_images import image_bytes_are_readable
from app.modules.sc.app.services.training_selection import (
    limit_sc_training_rows_per_class,
)
from app.modules.sc.capabilities import SC_PATCH_IMAGE_V1
from app.modules.sc.materialization.port.local import ScInspectionMaterializerPort
from app.modules.sc.runtime.data_source import open_sc_runtime_source
from app.modules.sc.runtime.materialized_input import parquet_paths_from_manifest
from app.shared.db.models.artifacts import ArtifactORM
from app.shared.api.schemas import ArtifactRef
from app.shared.domain.data_plane import DataPlaneManifest

logger = logging.getLogger(__name__)


def _runtime_logger() -> Any:
    try:
        return get_run_logger()
    except Exception:
        return logger


def _training_samples(
    manifest: DataPlaneManifest,
) -> tuple[list[Any], int]:
    from ml_library import TrainingSample
    from ml_library.data_loading import collect_parquet_dataset

    samples: list[Any] = []
    skipped = 0
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
            skipped += 1
            continue
        samples.append(
            TrainingSample(
                sample_id=str(row.get("sample_id", "")),
                defective_image=cast(bytes, defective),
                reference_image=cast(bytes, reference),
                label=label,
            )
        )
    return samples, skipped


async def _train_kernel(
    *,
    runtime_ctx: TrainingRuntimeContext,
    label_space: list[str],
    artifact_storage: Any,
    materialization_manifest: DataPlaneManifest,
    kernel: Callable[..., Any],
) -> dict[str, Any]:
    samples, skipped = _training_samples(materialization_manifest)
    sample_labels = {str(sample.label) for sample in samples}
    active_labels = [label for label in label_space if label in sample_labels]
    if len(active_labels) < 2:
        raise RuntimeExecutionError(
            "sc_training_insufficient_labels_after_image_filter",
            "SC training requires at least two labels after skipping unreadable images",
            details={"active_labels": active_labels, "skipped_samples": skipped},
        )
    output = kernel(samples, active_labels)
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
        "skipped_unreadable_samples": skipped,
    }


@dataclass(frozen=True, slots=True)
class _ScTrainingOutput:
    summary: dict[str, object]
    artifacts: tuple[ArtifactRef, ...]
    metrics: dict[str, object]
    issues: tuple[RuntimeIssueReported, ...]


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
        "source_collection_id": runtime_ctx.collection_id,
        "source_collection_revision_id": runtime_ctx.collection_revision_id,
    }


async def _run_sc_training(
    runtime_ctx: TrainingRuntimeContext,
    *,
    kernel: Callable[..., Any],
) -> _ScTrainingOutput:
    import app.registrations  # noqa: F401
    import polars as pl

    app_context = runtime_ctx.app_context
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    async with open_sc_runtime_source(
        runtime_ctx,
        with_labels=True,
        with_predictions=runtime_ctx.sample_filter is not None,
    ) as source:
        if source.dataset_type not in {"image_sc", "image_sc_collection"}:
            raise ValueError(
                f"SC trainer {runtime_ctx.trainer_id!r} requires image_sc data"
            )
        if SC_PATCH_IMAGE_V1.view_id not in source.view_types:
            raise ValueError(
                f"Runtime source does not provide {SC_PATCH_IMAGE_V1.view_id!r}"
            )
        rows = source.rows
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
                dataset_id=source.source_identity,
                job_id=runtime_ctx.job_id,
                image_types=["patch_template", "patch_defective"],
                max_output_bytes=(
                    app_context.shared.config.sc.pipeline.training_max_materialized_bytes
                ),
            )
            exit_stack.callback(materialization.cleanup)
            train_result = await _train_kernel(
                runtime_ctx=runtime_ctx,
                label_space=list(source.label_space),
                artifact_storage=app_context.shared.artifact_storage,
                materialization_manifest=materialization.manifest,
                kernel=kernel,
            )
        label_space = list(source.label_space)

    artifacts: list[dict[str, Any]] = [
        {
            "id": str(uuid.uuid4()),
            "uri": train_result["model_uri"],
            "kind": "model",
            "metadata": _trained_model_metadata(
                runtime_ctx=runtime_ctx,
                label_space=label_space,
                metadata=cast(dict[str, Any], train_result["metadata"]),
            ),
        }
    ]
    artifacts.extend(
        {
            "id": str(uuid.uuid4()),
            "uri": uri,
            "kind": "metrics",
            "metadata": {},
        }
        for uri in cast(list[str], train_result["artifact_uris"])
        if uri and uri != train_result["model_uri"]
    )
    async with app_context.shared.session_factory() as session:
        for artifact in artifacts:
            if not artifact["uri"]:
                continue
            session.add(
                ArtifactORM(
                    id=str(artifact["id"]),
                    job_id=runtime_ctx.job_id,
                    uri=str(artifact["uri"]),
                    kind=str(artifact["kind"]),
                    metadata_json=cast(dict[str, Any], artifact["metadata"]),
                )
            )
        await session.commit()
    produced_artifacts = tuple(
        ArtifactRef.model_validate(item) for item in artifacts if item["uri"]
    )
    issues: list[RuntimeIssueReported] = []
    materialization_error_count = len(materialization.errors)
    skipped_unreadable_samples = int(train_result["skipped_unreadable_samples"])
    if materialization_error_count or skipped_unreadable_samples:
        issues.append(
            RuntimeIssueReported(
                code="sc_training_images_skipped",
                message="SC training skipped unusable image samples",
                details={
                    "materialization_errors": materialization_error_count,
                    "unreadable_samples": skipped_unreadable_samples,
                },
            )
        )
    return _ScTrainingOutput(
        summary={"job_id": runtime_ctx.job_id, "status": "completed"},
        artifacts=produced_artifacts,
        metrics=cast(dict[str, object], train_result["metrics"]),
        issues=tuple(issues),
    )


async def resnet_sc_train(ctx: TrainingRuntimeContext) -> RuntimeEventStream:
    from ml_library import train_resnet

    output = await _run_sc_training(ctx, kernel=train_resnet)
    for issue in output.issues:
        yield issue
    for artifact in output.artifacts:
        yield ArtifactProduced(artifact)
    yield MetricsReported(output.metrics)
    yield OperationCompleted(output.summary)


async def yolo_sc_train(ctx: TrainingRuntimeContext) -> RuntimeEventStream:
    from ml_library import train_yolo

    output = await _run_sc_training(ctx, kernel=train_yolo)
    for issue in output.issues:
        yield issue
    for artifact in output.artifacts:
        yield ArtifactProduced(artifact)
    yield MetricsReported(output.metrics)
    yield OperationCompleted(output.summary)


__all__ = ["resnet_sc_train", "yolo_sc_train"]
