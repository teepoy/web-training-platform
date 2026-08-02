from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Generator, Iterator, Sequence
from typing import Any, Callable, cast

from app.core.registry import predictor
from app.modules.sc.runtime.materialized_input import parquet_paths_from_manifest
from app.shared.domain.data_plane import DataPlaneManifest
from app.shared.domain.runtime import ModelRef, PredictContext


def _checkpoint_bytes(artifact_storage: Any, uri: str) -> bytes:
    async def fetch() -> bytes:
        return cast(bytes, await artifact_storage.get_bytes(uri))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            lambda: asyncio.new_event_loop().run_until_complete(fetch())
        ).result()


def _prediction_samples(manifest: DataPlaneManifest) -> Iterator[Any]:
    from ml_library import PredictionSample
    from ml_library.data_loading import collect_parquet_dataset

    dataset = collect_parquet_dataset(parquet_paths_from_manifest(manifest))
    for row in dataset:
        yield PredictionSample(
            sample_id=str(row["sample_id"]),
            defective_image=(
                bytes(cast(bytes, row["patch_defective_bytes"]))
                if row.get("patch_defective_bytes") is not None
                else None
            ),
            reference_image=(
                bytes(cast(bytes, row["patch_template_bytes"]))
                if row.get("patch_template_bytes") is not None
                else None
            ),
        )


def _predict(
    *,
    artifact_storage: Any,
    model_ref: ModelRef,
    materialization_manifest: DataPlaneManifest,
    kernel: Callable[..., Any],
    label_space: Sequence[str] | None = None,
) -> Generator[dict[str, Any], None, None]:
    if artifact_storage is None:
        raise ValueError("artifact_storage is required for SC prediction")
    if not model_ref.uri:
        raise ValueError("model_ref.uri is required")
    checkpoint = _checkpoint_bytes(artifact_storage, model_ref.uri)
    samples = _prediction_samples(materialization_manifest)
    outputs = (
        kernel(checkpoint, list(label_space), samples)
        if label_space is not None
        else kernel(checkpoint, samples)
    )
    for output in outputs:
        result: dict[str, Any] = {
            "sample_id": output.sample_id,
            "label": output.label,
            "confidence": output.confidence,
        }
        if output.scores:
            result["scores"] = dict(output.scores)
        if output.error is not None:
            result["error"] = output.error
        yield result


@predictor(id="resnet50-sc-v1")
def resnet_sc_predictor(
    *,
    artifact_storage: Any,
    ctx: PredictContext,
    model_ref: ModelRef,
    materialization_manifest: DataPlaneManifest,
) -> Generator[dict[str, Any], None, None]:
    del ctx
    from ml_library import predict_resnet

    yield from _predict(
        artifact_storage=artifact_storage,
        model_ref=model_ref,
        materialization_manifest=materialization_manifest,
        kernel=predict_resnet,
    )


@predictor(id="yolo-sc-v1")
def yolo_sc_predictor(
    *,
    artifact_storage: Any,
    ctx: PredictContext,
    model_ref: ModelRef,
    materialization_manifest: DataPlaneManifest,
) -> Generator[dict[str, Any], None, None]:
    del ctx
    metadata_labels = model_ref.metadata.get("label_space", [])
    if not isinstance(metadata_labels, Sequence) or isinstance(
        metadata_labels, (str, bytes)
    ):
        raise ValueError("YOLO model metadata must include compact label_space")
    labels = [str(label) for label in metadata_labels]
    if not labels:
        raise ValueError("YOLO model metadata must include compact label_space")
    from ml_library import predict_yolo

    yield from _predict(
        artifact_storage=artifact_storage,
        model_ref=model_ref,
        materialization_manifest=materialization_manifest,
        kernel=predict_yolo,
        label_space=labels,
    )
