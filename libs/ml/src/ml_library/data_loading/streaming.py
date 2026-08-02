from __future__ import annotations

import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from torch.utils.data import IterableDataset, get_worker_info

from ml_library.data_loading._parquet import (
    ROW_INDEX_COLUMN,
    ParquetPaths,
    inspect_parquet_sources,
)


@dataclass(frozen=True, slots=True)
class _RowGroup:
    path: str
    index: int
    row_offset: int


class StreamingParquetDataset(IterableDataset[dict[str, Any]]):
    """A row-group-partitioned Parquet stream with bounded-memory shuffle."""

    def __init__(
        self,
        paths: ParquetPaths,
        *,
        columns: Sequence[str] | None,
        shuffle: bool,
        seed: int,
        shuffle_buffer_rows: int,
    ) -> None:
        super().__init__()
        if shuffle_buffer_rows <= 0:
            raise ValueError("shuffle_buffer_rows must be greater than zero")

        sources, normalized_columns = inspect_parquet_sources(paths, columns=columns)
        row_groups: list[_RowGroup] = []
        row_offset = 0
        for source in sources:
            for row_group_index, row_group_size in enumerate(source.row_group_sizes):
                row_groups.append(
                    _RowGroup(
                        path=str(source.path),
                        index=row_group_index,
                        row_offset=row_offset,
                    )
                )
                row_offset += row_group_size

        self._columns = normalized_columns
        self._shuffle = shuffle
        self._seed = seed
        self._shuffle_buffer_rows = shuffle_buffer_rows
        self._row_groups = tuple(row_groups)
        self._row_count = row_offset
        self._epoch = 0

    @property
    def row_count(self) -> int:
        return self._row_count

    def __len__(self) -> int:
        return self._row_count

    def set_epoch(self, epoch: int) -> None:
        if epoch < 0:
            raise ValueError("epoch must be non-negative")
        self._epoch = epoch

    def __iter__(self) -> Iterator[dict[str, Any]]:
        worker = get_worker_info()
        worker_id = worker.id if worker is not None else 0
        worker_count = worker.num_workers if worker is not None else 1
        epoch_seed = self._seed + self._epoch * 1_000_003
        row_groups = list(self._row_groups)
        if self._shuffle:
            random.Random(epoch_seed).shuffle(row_groups)
        assigned_row_groups = row_groups[worker_id::worker_count]

        randomizer = random.Random(epoch_seed + worker_id * 10_007)
        rows = self._read_rows(assigned_row_groups, randomizer)
        if self._shuffle:
            yield from self._shuffle_rows(rows, randomizer)
        else:
            yield from rows

    def _read_rows(
        self,
        row_groups: list[_RowGroup],
        randomizer: random.Random,
    ) -> Iterator[dict[str, Any]]:
        parquet_files: dict[str, pq.ParquetFile] = {}
        try:
            for row_group in row_groups:
                parquet_file = parquet_files.get(row_group.path)
                if parquet_file is None:
                    parquet_file = pq.ParquetFile(row_group.path)
                    parquet_files[row_group.path] = parquet_file
                table = parquet_file.read_row_group(
                    row_group.index,
                    columns=(
                        list(self._columns) if self._columns is not None else None
                    ),
                )
                indices = pa.array(
                    range(row_group.row_offset, row_group.row_offset + table.num_rows),
                    type=pa.uint64(),
                )
                rows = table.append_column(ROW_INDEX_COLUMN, indices).to_pylist()
                if self._shuffle:
                    randomizer.shuffle(rows)
                yield from rows
        finally:
            for parquet_file in parquet_files.values():
                parquet_file.close()

    def _shuffle_rows(
        self,
        rows: Iterator[dict[str, Any]],
        randomizer: random.Random,
    ) -> Iterator[dict[str, Any]]:
        buffer: list[dict[str, Any]] = []
        for row in rows:
            if len(buffer) < self._shuffle_buffer_rows:
                buffer.append(row)
                continue
            selected = randomizer.randrange(len(buffer))
            yield buffer[selected]
            buffer[selected] = row
        randomizer.shuffle(buffer)
        yield from buffer


def stream_parquet_dataset(
    paths: ParquetPaths,
    *,
    columns: Sequence[str] | None = None,
    shuffle: bool,
    seed: int,
    shuffle_buffer_rows: int,
) -> StreamingParquetDataset:
    """Build a Torch IterableDataset without materializing the Parquet rows.

    DataLoader must use ``shuffle=False``. With workers, row groups are shuffled
    once and then partitioned disjointly, so each physical row appears once per
    epoch. Call ``set_epoch`` before creating each epoch iterator. In particular,
    do not combine epoch mutation with ``persistent_workers=True``.
    """

    return StreamingParquetDataset(
        paths,
        columns=columns,
        shuffle=shuffle,
        seed=seed,
        shuffle_buffer_rows=shuffle_buffer_rows,
    )
