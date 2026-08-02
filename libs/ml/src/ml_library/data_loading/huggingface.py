from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow as pa

from ml_library.data_loading._parquet import ROW_INDEX_COLUMN

if TYPE_CHECKING:
    from datasets import Dataset


_PARQUET_SUFFIXES = {".parquet", ".pq"}


def open_hf_arrow_dataset(
    path: str | os.PathLike[str],
    *,
    expected_schema: pa.Schema | None = None,
) -> Dataset:
    """Memory-map an Arrow IPC stream as a Hugging Face map-style dataset.

    This function creates no Hugging Face cache. The input file is caller-owned
    and must outlive the returned dataset and every DataLoader worker using it.
    """

    arrow_path = Path(path)
    if arrow_path.suffix.lower() in _PARQUET_SUFFIXES:
        raise ValueError(
            "HF indexed loading requires an Arrow IPC stream file; received "
            "Parquet. Materialize the dataset view with "
            "preferred_format='arrow_ipc' before loading."
        )
    if not arrow_path.is_file():
        raise FileNotFoundError(f"Arrow input does not exist: {arrow_path}")

    try:
        with pa.memory_map(str(arrow_path), "r") as source:
            schema = pa.ipc.open_stream(source).schema
    except (OSError, pa.ArrowException) as exc:
        raise ValueError(
            "HF indexed loading requires an Arrow IPC stream produced with "
            "pyarrow.ipc.new_stream(); Parquet, Feather, and the Arrow IPC file "
            "container are not accepted."
        ) from exc

    if ROW_INDEX_COLUMN not in schema.names:
        raise ValueError(
            f"Arrow input must contain the materialized {ROW_INDEX_COLUMN!r} column"
        )
    index_type = schema.field(ROW_INDEX_COLUMN).type
    if not pa.types.is_integer(index_type):
        raise ValueError(f"Arrow column {ROW_INDEX_COLUMN!r} must have integer type")
    if expected_schema is not None and not schema.equals(
        expected_schema,
        check_metadata=False,
    ):
        raise ValueError("Arrow input schema does not match expected_schema")

    try:
        from datasets import Dataset
    except ImportError as exc:
        raise RuntimeError(
            "open_hf_arrow_dataset requires ml-library[huggingface]"
        ) from exc

    return Dataset.from_file(str(arrow_path), in_memory=False)
