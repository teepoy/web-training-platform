from __future__ import annotations

import io
from collections.abc import Iterator, Sequence

from PIL import Image

from ml_library.data_loading._parquet import ParquetPaths
from ml_library.data_loading.streaming import stream_parquet_dataset
from ml_library.models import PredictionSample, TrainingSample

_SC_TRAINING_COLUMNS = (
    "sample_id",
    "label",
    "patch_defective_bytes",
    "patch_template_bytes",
)
_SC_PREDICTION_COLUMNS = (
    "sample_id",
    "patch_defective_bytes",
    "patch_template_bytes",
)


def inspect_sc_training_samples(
    paths: ParquetPaths,
    label_space: Sequence[str],
) -> tuple[tuple[str, ...], int, int]:
    """Return active labels, valid sample count, and unreadable sample count."""

    active: set[str] = set()
    valid_samples = 0
    skipped_unreadable_samples = 0
    for row in _training_rows(
        paths,
        shuffle=False,
        seed=0,
        shuffle_buffer_rows=1,
        epoch=0,
    ):
        sample = _training_sample(row)
        if sample is None:
            if row.get("label"):
                skipped_unreadable_samples += 1
            continue
        active.add(sample.label)
        valid_samples += 1
    declared = [label for label in label_space if label in active]
    labels = tuple(declared + sorted(active - set(declared)))
    return labels, valid_samples, skipped_unreadable_samples


def iter_sc_training_samples(
    paths: ParquetPaths,
    *,
    shuffle: bool,
    seed: int,
    shuffle_buffer_rows: int,
    epoch: int = 0,
) -> Iterator[TrainingSample]:
    for row in _training_rows(
        paths,
        shuffle=shuffle,
        seed=seed,
        shuffle_buffer_rows=shuffle_buffer_rows,
        epoch=epoch,
    ):
        sample = _training_sample(row)
        if sample is not None:
            yield sample


def iter_sc_prediction_samples(paths: ParquetPaths) -> Iterator[PredictionSample]:
    rows = stream_parquet_dataset(
        paths,
        columns=_SC_PREDICTION_COLUMNS,
        shuffle=False,
        seed=0,
        shuffle_buffer_rows=1,
    )
    for row in rows:
        yield PredictionSample(
            sample_id=str(row.get("sample_id") or ""),
            defective_image=_optional_bytes(row.get("patch_defective_bytes")),
            reference_image=_optional_bytes(row.get("patch_template_bytes")),
        )


def _training_rows(
    paths: ParquetPaths,
    *,
    shuffle: bool,
    seed: int,
    shuffle_buffer_rows: int,
    epoch: int,
) -> Iterator[dict[str, object]]:
    rows = stream_parquet_dataset(
        paths,
        columns=_SC_TRAINING_COLUMNS,
        shuffle=shuffle,
        seed=seed,
        shuffle_buffer_rows=shuffle_buffer_rows,
    )
    rows.set_epoch(epoch)
    yield from rows


def _training_sample(row: dict[str, object]) -> TrainingSample | None:
    label_value = row.get("label")
    label = str(label_value).strip() if label_value is not None else ""
    if not label:
        return None
    defective = _readable_image_bytes(row.get("patch_defective_bytes"))
    reference = _readable_image_bytes(row.get("patch_template_bytes"))
    if defective is None or reference is None:
        return None
    return TrainingSample(
        sample_id=str(row.get("sample_id") or ""),
        defective_image=defective,
        reference_image=reference,
        label=label,
    )


def _readable_image_bytes(value: object) -> bytes | None:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytearray):
        value = bytes(value)
    if not isinstance(value, bytes) or not value:
        return None
    try:
        with Image.open(io.BytesIO(value)) as image:
            image.verify()
    except (OSError, ValueError):
        return None
    return value


def _optional_bytes(value: object) -> bytes | None:
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, bytearray):
        return bytes(value)
    return value if isinstance(value, bytes) else None


__all__ = [
    "inspect_sc_training_samples",
    "iter_sc_prediction_samples",
    "iter_sc_training_samples",
]
