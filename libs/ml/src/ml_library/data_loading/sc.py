from __future__ import annotations

import io
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from PIL import Image
from torch.utils.data import IterableDataset

from ml_library.data_loading._parquet import ParquetPaths
from ml_library.data_loading.streaming import stream_parquet_dataset
from ml_library.models import PredictionSample, TrainingSample

_SC_TRAINING_COLUMNS = (
    "sample_id",
    "label",
    "patch_defective_bytes",
    "patch_template_bytes",
)


@dataclass(frozen=True, slots=True)
class ScTrainingDatasetSummary:
    active_labels: tuple[str, ...]
    valid_samples: int
    skipped_unreadable_samples: int


class ScTrainingDataset(IterableDataset[TrainingSample]):
    """Replayable, bounded-memory SC training samples backed by Parquet."""

    def __init__(
        self,
        paths: ParquetPaths,
        *,
        shuffle: bool,
        seed: int,
        shuffle_buffer_rows: int,
    ) -> None:
        super().__init__()
        self._rows = stream_parquet_dataset(
            paths,
            columns=_SC_TRAINING_COLUMNS,
            shuffle=shuffle,
            seed=seed,
            shuffle_buffer_rows=shuffle_buffer_rows,
        )
        self._summary: ScTrainingDatasetSummary | None = None

    @property
    def row_count(self) -> int:
        return self._rows.row_count

    @property
    def summary(self) -> ScTrainingDatasetSummary | None:
        return self._summary

    def __len__(self) -> int:
        if self._summary is None:
            raise RuntimeError("Inspect ScTrainingDataset before requesting its length")
        return self._summary.valid_samples

    def set_epoch(self, epoch: int) -> None:
        self._rows.set_epoch(epoch)

    def inspect(self, label_space: Sequence[str]) -> ScTrainingDatasetSummary:
        if self._summary is not None:
            return self._summary

        active: set[str] = set()
        valid_samples = 0
        skipped_unreadable_samples = 0
        for row in self._rows:
            sample = _training_sample(row)
            if sample is None:
                if row.get("label"):
                    skipped_unreadable_samples += 1
                continue
            active.add(sample.label)
            valid_samples += 1
        declared = [label for label in label_space if label in active]
        labels = declared + sorted(active - set(declared))
        self._summary = ScTrainingDatasetSummary(
            active_labels=tuple(labels),
            valid_samples=valid_samples,
            skipped_unreadable_samples=skipped_unreadable_samples,
        )
        return self._summary

    def __iter__(self) -> Iterator[TrainingSample]:
        for row in self._rows:
            sample = _training_sample(row)
            if sample is not None:
                yield sample


class ScPredictionDataset(IterableDataset[PredictionSample]):
    """Replayable, bounded-memory SC prediction samples backed by Parquet."""

    def __init__(self, paths: ParquetPaths) -> None:
        super().__init__()
        self._rows = stream_parquet_dataset(
            paths,
            columns=(
                "sample_id",
                "patch_defective_bytes",
                "patch_template_bytes",
            ),
            shuffle=False,
            seed=0,
            shuffle_buffer_rows=1,
        )

    def __len__(self) -> int:
        return self._rows.row_count

    def __iter__(self) -> Iterator[PredictionSample]:
        for row in self._rows:
            yield PredictionSample(
                sample_id=str(row.get("sample_id") or ""),
                defective_image=_optional_bytes(row.get("patch_defective_bytes")),
                reference_image=_optional_bytes(row.get("patch_template_bytes")),
            )


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
    "ScPredictionDataset",
    "ScTrainingDataset",
    "ScTrainingDatasetSummary",
]
