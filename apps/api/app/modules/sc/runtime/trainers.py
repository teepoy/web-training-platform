from __future__ import annotations

import json
import logging
from typing import Any, Callable, cast

from prefect import get_run_logger

from app.core.registry import trainer
from app.modules.sc.app.services.training_images import image_bytes_are_readable
from app.modules.sc.runtime.materialized_input import parquet_paths_from_manifest
from app.shared.domain.data_plane import DataPlaneManifest
from app.shared.domain.runtime import TrainContext, TrainResult

logger = logging.getLogger(__name__)


def _runtime_logger() -> Any:
    try:
        return get_run_logger()
    except Exception:
        return logger


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


async def _train(
    ctx: TrainContext,
    *,
    artifact_storage: Any,
    materialization_manifest: DataPlaneManifest,
    kernel: Callable[..., Any],
    missing_image_policy: str,
) -> TrainResult:
    if artifact_storage is None:
        raise ValueError(f"artifact_storage is required for {ctx.trainer_id} training")
    samples = _training_samples(
        materialization_manifest,
        missing_image_policy=missing_image_policy,
    )
    output = kernel(samples, list(ctx.dataset_ref.label_space))
    checkpoint_object = f"models/{ctx.job_id}/checkpoint.pt"
    metrics_object = f"models/{ctx.job_id}/metrics.json"
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
    _runtime_logger().info(
        "SC training completed trainer_id=%s samples=%d",
        ctx.trainer_id,
        len(samples),
    )
    return TrainResult(
        model_uri=model_uri,
        metrics=dict(output.metrics),
        artifact_uris=[model_uri, metrics_uri],
        metadata=dict(output.metadata),
    )


@trainer(id="resnet50-sc-v1")
async def resnet_sc_train(
    ctx: TrainContext,
    *,
    artifact_storage: Any = None,
    materialization_manifest: DataPlaneManifest,
    **kwargs: Any,
) -> TrainResult:
    from ml_library import train_resnet

    return await _train(
        ctx,
        artifact_storage=artifact_storage,
        materialization_manifest=materialization_manifest,
        kernel=train_resnet,
        missing_image_policy=str(kwargs.get("missing_image_policy") or "fail"),
    )


@trainer(id="yolo-sc-v1")
async def yolo_sc_train(
    ctx: TrainContext,
    *,
    artifact_storage: Any = None,
    materialization_manifest: DataPlaneManifest,
    **kwargs: Any,
) -> TrainResult:
    from ml_library import train_yolo

    return await _train(
        ctx,
        artifact_storage=artifact_storage,
        materialization_manifest=materialization_manifest,
        kernel=train_yolo,
        missing_image_policy=str(kwargs.get("missing_image_policy") or "fail"),
    )
