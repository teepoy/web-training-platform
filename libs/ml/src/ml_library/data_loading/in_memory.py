from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from torch.utils.data import Dataset

from ml_library.data_loading._parquet import (
    ROW_INDEX_COLUMN,
    ParquetPaths,
    inspect_parquet_sources,
)


class InMemoryArrowDataset(Dataset[dict[str, Any]]):
    """A small map-style Torch dataset backed by a fully collected Arrow table."""

    def __init__(self, table: pa.Table) -> None:
        self._table = table

    @property
    def table(self) -> pa.Table:
        return self._table

    def __len__(self) -> int:
        return self._table.num_rows

    def __getitem__(self, index: int) -> dict[str, Any]:
        row_count = len(self)
        if index < 0:
            index += row_count
        if index < 0 or index >= row_count:
            raise IndexError(index)
        return self._table.slice(index, 1).to_pylist()[0]


def collect_parquet_dataset(
    paths: ParquetPaths,
    *,
    columns: Sequence[str] | None = None,
) -> InMemoryArrowDataset:
    """Collect Parquet inputs and return a map-style dataset.

    ``__row_index`` is generated from the explicit input path order followed by
    each file's physical row order. Callers can use ``DataLoader(shuffle=True)``.
    """

    sources, normalized_columns = inspect_parquet_sources(paths, columns=columns)
    tables: list[pa.Table] = []
    row_offset = 0
    for source in sources:
        read_columns = (
            list(normalized_columns) if normalized_columns is not None else None
        )
        table = pq.read_table(source.path, columns=read_columns)
        indices = pa.array(
            range(row_offset, row_offset + table.num_rows),
            type=pa.uint64(),
        )
        tables.append(table.append_column(ROW_INDEX_COLUMN, indices))
        row_offset += table.num_rows

    return InMemoryArrowDataset(pa.concat_tables(tables))
