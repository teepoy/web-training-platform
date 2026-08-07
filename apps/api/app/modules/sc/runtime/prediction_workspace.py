from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.modules.runtime.domain.context import PredictionRuntimeContext
from app.modules.sc.materialization.port.local import ScInspectionMaterializerPort
from app.modules.sc.runtime.materialized_input import parquet_paths_from_manifest

if TYPE_CHECKING:
    from ml_library.data_loading import ScPredictionDataset


@dataclass(frozen=True, slots=True)
class ScPredictionWorkspace:
    dataset: ScPredictionDataset
    checkpoint_path: Path
    materialization_error_count: int


@asynccontextmanager
async def open_sc_prediction_workspace(
    runtime_ctx: PredictionRuntimeContext,
    *,
    rows: Any,
    source_identity: str,
    model_uri: str,
) -> AsyncIterator[ScPredictionWorkspace]:
    from ml_library.data_loading import ScPredictionDataset

    if not model_uri:
        raise ValueError("model URI is required")
    app_context = runtime_ctx.app_context
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    materializer = app_context.injector.get(ScInspectionMaterializerPort)
    materialization = await materializer.materialize(
        rows_lazyframe=rows,
        dataset_id=source_identity,
        job_id=runtime_ctx.job_id,
        image_types=["patch_template", "patch_defective"],
        max_output_bytes=(
            app_context.shared.config.sc.pipeline.prediction_max_materialized_bytes
        ),
    )
    try:
        with tempfile.TemporaryDirectory(
            prefix=f"sc-prediction-{runtime_ctx.job_id}-"
        ) as temporary_directory:
            checkpoint_path = Path(temporary_directory) / "model.pt"
            await app_context.shared.artifact_storage.get_file(
                model_uri,
                str(checkpoint_path),
            )
            yield ScPredictionWorkspace(
                dataset=ScPredictionDataset(
                    parquet_paths_from_manifest(materialization.manifest)
                ),
                checkpoint_path=checkpoint_path,
                materialization_error_count=len(materialization.errors),
            )
    finally:
        materialization.cleanup()


__all__ = ["ScPredictionWorkspace", "open_sc_prediction_workspace"]
