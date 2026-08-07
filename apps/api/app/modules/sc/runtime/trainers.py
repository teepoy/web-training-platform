from __future__ import annotations

import logging
import tempfile
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from prefect import get_run_logger

from app.modules.runtime.domain.context import TrainingRuntimeContext
from app.modules.runtime.domain.events import (
    ArtifactOutput,
    LocalArtifactFile,
    MetricsReported,
    OperationCompleted,
    RuntimeEventStream,
    RuntimeExecutionError,
    RuntimeIssueReported,
)
from app.modules.sc.app.services.sample_filter import (
    parse_and_apply_workflow_sample_filter,
)
from app.modules.sc.app.services.training_selection import (
    limit_sc_training_rows_per_class,
)
from app.modules.sc.capabilities import SC_PATCH_IMAGE_V1
from app.modules.sc.materialization.port.local import ScInspectionMaterializerPort
from app.modules.sc.runtime.data_source import open_sc_runtime_source
from app.modules.sc.runtime.materialized_input import parquet_paths_from_manifest

if TYPE_CHECKING:
    from ml_library.data_loading import ScTrainingDataset, ScTrainingDatasetSummary
    from ml_library.models import TrainingOutput

logger = logging.getLogger(__name__)


class _TrainModel(Protocol):
    def __call__(
        self,
        samples: ScTrainingDataset,
        label_space: Sequence[str],
        *,
        work_dir: Path,
    ) -> TrainingOutput: ...


@dataclass(frozen=True, slots=True)
class _ScTrainingWorkspace:
    dataset: ScTrainingDataset
    work_dir: Path
    materialization_error_count: int


def _runtime_logger() -> Any:
    try:
        return get_run_logger()
    except Exception:
        return logger


@asynccontextmanager
async def _open_sc_training_workspace(
    runtime_ctx: TrainingRuntimeContext,
    *,
    rows: Any,
    source_identity: str,
) -> AsyncIterator[_ScTrainingWorkspace]:
    from ml_library.data_loading import ScTrainingDataset

    app_context = runtime_ctx.app_context
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    pipeline_config = app_context.shared.config.sc.pipeline
    materializer = app_context.injector.get(ScInspectionMaterializerPort)
    materialization = await materializer.materialize(
        rows_lazyframe=rows,
        dataset_id=source_identity,
        job_id=runtime_ctx.job_id,
        image_types=["patch_template", "patch_defective"],
        max_output_bytes=pipeline_config.training_max_materialized_bytes,
    )
    try:
        with tempfile.TemporaryDirectory(
            prefix=f"sc-training-{runtime_ctx.job_id}-"
        ) as temporary_directory:
            dataset = ScTrainingDataset(
                parquet_paths_from_manifest(materialization.manifest),
                shuffle=True,
                seed=pipeline_config.training_shuffle_seed,
                shuffle_buffer_rows=pipeline_config.training_shuffle_buffer_rows,
            )
            yield _ScTrainingWorkspace(
                dataset=dataset,
                work_dir=Path(temporary_directory),
                materialization_error_count=len(materialization.errors),
            )
    finally:
        materialization.cleanup()


def _inspect_training_dataset(
    dataset: ScTrainingDataset,
    label_space: Sequence[str],
) -> ScTrainingDatasetSummary:
    summary = dataset.inspect(label_space)
    if len(summary.active_labels) < 2:
        raise RuntimeExecutionError(
            "sc_training_insufficient_labels_after_image_filter",
            "SC training requires at least two labels after skipping unreadable images",
            details={
                "active_labels": list(summary.active_labels),
                "skipped_samples": summary.skipped_unreadable_samples,
            },
        )
    return summary


def _trained_model_metadata(
    *,
    runtime_ctx: TrainingRuntimeContext,
    label_space: Sequence[str],
    metadata: dict[str, object],
) -> dict[str, object]:
    from app.modules.runtime.catalog import runtime_catalog

    trainer = runtime_catalog.get_trainer_meta(runtime_ctx.trainer_id)
    runtime_labels = metadata.get("label_space")
    if not isinstance(runtime_labels, list):
        runtime_labels = list(label_space)
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


def _model_artifact_id(job_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"web-training-platform:runtime-artifact:{job_id}:model",
        )
    )


async def _run_sc_training(
    runtime_ctx: TrainingRuntimeContext,
    *,
    train_model: _TrainModel,
) -> RuntimeEventStream:
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

        _runtime_logger().info(
            "SC trainer materializing input: trainer=%s rows=%d",
            runtime_ctx.trainer_id,
            selected_rows,
        )
        label_space = list(source.label_space)
        async with _open_sc_training_workspace(
            runtime_ctx,
            rows=rows,
            source_identity=source.source_identity,
        ) as workspace:
            dataset_summary = _inspect_training_dataset(
                workspace.dataset,
                label_space,
            )
            output = train_model(
                workspace.dataset,
                dataset_summary.active_labels,
                work_dir=workspace.work_dir,
            )
            if (
                workspace.materialization_error_count
                or dataset_summary.skipped_unreadable_samples
            ):
                yield RuntimeIssueReported(
                    code="sc_training_images_skipped",
                    message="SC training skipped unusable image samples",
                    details={
                        "materialization_errors": (
                            workspace.materialization_error_count
                        ),
                        "unreadable_samples": (
                            dataset_summary.skipped_unreadable_samples
                        ),
                    },
                )
            yield ArtifactOutput(
                id=_model_artifact_id(runtime_ctx.job_id),
                kind="model",
                payload=LocalArtifactFile(
                    path=output.checkpoint_path,
                    object_name=f"models/{runtime_ctx.job_id}/checkpoint.pt",
                    content_type="application/octet-stream",
                ),
                metadata=_trained_model_metadata(
                    runtime_ctx=runtime_ctx,
                    label_space=label_space,
                    metadata=dict(output.metadata),
                ),
                name="checkpoint.pt",
                format="pytorch",
            )
            yield MetricsReported(dict(output.metrics))
            yield OperationCompleted(
                {"job_id": runtime_ctx.job_id, "status": "completed"}
            )


async def resnet_sc_train(ctx: TrainingRuntimeContext) -> RuntimeEventStream:
    from ml_library import train_resnet

    async for event in _run_sc_training(ctx, train_model=train_resnet):
        yield event


async def yolo_sc_train(ctx: TrainingRuntimeContext) -> RuntimeEventStream:
    from ml_library import train_yolo

    async for event in _run_sc_training(ctx, train_model=train_yolo):
        yield event


__all__ = ["resnet_sc_train", "yolo_sc_train"]
