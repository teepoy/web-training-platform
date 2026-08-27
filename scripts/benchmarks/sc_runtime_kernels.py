"""Fake SC kernels used only by the runtime data-path benchmark."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow.parquet as pq

if TYPE_CHECKING:
    from ml_library.models import Prediction, TrainingOutput


async def fake_train_yolo(
    parquet_paths: str | os.PathLike[str] | Sequence[str | os.PathLike[str]],
    label_space: Sequence[str],
    *,
    valid_samples: int,
    work_dir: Path,
    shuffle_seed: int,
    on_epoch: Callable[[int, int, float, float, float], Awaitable[None]] | None = None,
    **_unused: object,
) -> TrainingOutput:
    """Consume every materialized row without importing a GPU model."""

    from ml_library.models import TrainingOutput

    del shuffle_seed
    paths = (
        (Path(parquet_paths),)
        if isinstance(parquet_paths, (str, os.PathLike))
        else tuple(Path(path) for path in parquet_paths)
    )
    consumed = 0
    input_bytes = 0
    columns = (
        "sample_id",
        "label",
        "patch_defective_bytes",
        "patch_template_bytes",
    )
    for path in paths:
        parquet_file = pq.ParquetFile(path)
        for batch in parquet_file.iter_batches(columns=columns):
            consumed += batch.num_rows
            input_bytes += batch.nbytes
    if consumed != valid_samples:
        raise RuntimeError(
            f"fake SC trainer expected {valid_samples} rows, consumed {consumed}"
        )

    labels = [str(label) for label in label_space]
    work_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = work_dir / "checkpoint.pt"
    checkpoint_path.write_bytes(b"fake-sc-training-checkpoint\n")
    if on_epoch is not None:
        await on_epoch(1, 1, 0.0, 0.0, 1.0)
    return TrainingOutput(
        checkpoint_path=checkpoint_path,
        metrics={
            "benchmark_kernel": "fake",
            "num_samples": consumed,
            "num_classes": len(labels),
            "input_bytes": input_bytes,
        },
        metadata={
            "runtime": "fake-sc-data-path-benchmark-v1",
            "benchmark_kernel": "fake",
            "trained_samples": consumed,
            "label_space": labels,
            "image_roles": ["patch_defective", "patch_template"],
        },
    )


async def fake_predict_yolo_stream(
    checkpoint_path: Path,
    label_space: Sequence[str],
    samples: AsyncIterator[dict[str, object]],
    **_unused: object,
) -> AsyncIterator[Prediction]:
    """Consume the resolved image stream and emit deterministic predictions."""

    from ml_library.models import Prediction

    if not checkpoint_path.is_file():
        raise FileNotFoundError(checkpoint_path)
    labels = [str(label) for label in label_space]
    if not labels:
        raise ValueError("fake SC predictor requires at least one label")
    scores = {label: 1.0 if index == 0 else 0.0 for index, label in enumerate(labels)}

    async for sample in samples:
        sample_id = str(sample.get("sample_id") or "")
        source_error = sample.get("error")
        error = str(source_error) if source_error else None
        if error is None and not (
            _has_bytes(sample.get("patch_defective_bytes"))
            and _has_bytes(sample.get("patch_template_bytes"))
        ):
            error = "benchmark input missing patch image bytes"
        if error is not None:
            yield Prediction(
                sample_id=sample_id,
                label="",
                confidence=None,
                error=error,
            )
            continue
        yield Prediction(
            sample_id=sample_id,
            label=labels[0],
            confidence=1.0,
            scores=dict(scores),
        )


def _has_bytes(value: object) -> bool:
    return isinstance(value, (bytes, bytearray, memoryview)) and bool(value)


__all__ = ["fake_predict_yolo_stream", "fake_train_yolo"]
