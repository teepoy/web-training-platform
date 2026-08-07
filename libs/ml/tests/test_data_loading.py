from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from torch.utils.data import DataLoader

from ml_library.data_loading import (
    ROW_INDEX_COLUMN,
    ScPredictionDataset,
    ScTrainingDataset,
    StreamingParquetDataset,
    collect_parquet_dataset,
    open_hf_arrow_dataset,
    stream_parquet_dataset,
)


def _image_bytes(color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), color=color).save(output, "PNG")
    return output.getvalue()


def _rows(count: int, *, offset: int = 0) -> pa.Table:
    return pa.table(
        {
            "value": range(offset, offset + count),
            "text": [f"row-{index}" for index in range(offset, offset + count)],
        }
    )


def _write_parquet(path: Path, table: pa.Table, *, row_group_size: int = 8) -> None:
    pq.write_table(table, path, row_group_size=row_group_size)


def _write_arrow_stream(path: Path, table: pa.Table) -> None:
    with pa.OSFile(str(path), "wb") as sink:
        with pa.ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)


def _stream_indices(
    dataset: StreamingParquetDataset,
    *,
    workers: int,
) -> list[int]:
    loader = DataLoader(
        dataset,
        batch_size=None,
        shuffle=False,
        num_workers=workers,
        persistent_workers=False,
    )
    return [row[ROW_INDEX_COLUMN] for row in loader]


def test_collect_parquet_dataset_is_map_style_and_generates_stable_index(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.parquet"
    second = tmp_path / "second.parquet"
    _write_parquet(first, _rows(5))
    _write_parquet(second, _rows(4, offset=5))

    dataset = collect_parquet_dataset([first, second], columns=["value"])

    assert len(dataset) == 9
    assert dataset[0] == {"value": 0, ROW_INDEX_COLUMN: 0}
    assert dataset[-1] == {"value": 8, ROW_INDEX_COLUMN: 8}
    assert dataset.table.column_names == ["value", ROW_INDEX_COLUMN]
    with pytest.raises(IndexError):
        dataset[9]

    shuffled = DataLoader(
        dataset,
        batch_size=None,
        shuffle=True,
    )
    shuffled_indices = [row[ROW_INDEX_COLUMN] for row in shuffled]
    assert sorted(shuffled_indices) == list(range(9))


def test_parquet_loaders_reject_the_reserved_index_column(tmp_path: Path) -> None:
    path = tmp_path / "indexed.parquet"
    table = _rows(3).append_column(ROW_INDEX_COLUMN, pa.array([0, 1, 2]))
    _write_parquet(path, table)

    with pytest.raises(ValueError, match="reserved column"):
        collect_parquet_dataset(path)
    with pytest.raises(ValueError, match="reserved column"):
        stream_parquet_dataset(
            path,
            shuffle=True,
            seed=1,
            shuffle_buffer_rows=2,
        )


def test_stream_parquet_dataset_shuffles_without_duplicates_with_four_workers(
    tmp_path: Path,
) -> None:
    paths: list[Path] = []
    for shard in range(3):
        path = tmp_path / f"shard-{shard}.parquet"
        _write_parquet(path, _rows(32, offset=shard * 32), row_group_size=4)
        paths.append(path)

    dataset = stream_parquet_dataset(
        paths,
        columns=["value"],
        shuffle=True,
        seed=712,
        shuffle_buffer_rows=11,
    )
    indices = _stream_indices(dataset, workers=4)

    assert len(dataset) == 96
    assert len(indices) == 96
    assert len(set(indices)) == 96
    assert sorted(indices) == list(range(96))
    assert indices != list(range(96))


def test_stream_parquet_dataset_replays_an_epoch_and_changes_between_epochs(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rows.parquet"
    _write_parquet(path, _rows(40), row_group_size=5)
    dataset = stream_parquet_dataset(
        path,
        shuffle=True,
        seed=33,
        shuffle_buffer_rows=7,
    )

    first = _stream_indices(dataset, workers=0)
    replay = _stream_indices(dataset, workers=0)
    dataset.set_epoch(1)
    second = _stream_indices(dataset, workers=0)

    assert replay == first
    assert second != first
    assert sorted(second) == sorted(first) == list(range(40))


def test_stream_parquet_dataset_requires_dataloader_shuffle_false(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rows.parquet"
    _write_parquet(path, _rows(3))
    dataset = stream_parquet_dataset(
        path,
        shuffle=True,
        seed=1,
        shuffle_buffer_rows=2,
    )

    with pytest.raises(ValueError, match="IterableDataset"):
        DataLoader(dataset, batch_size=None, shuffle=True)


def test_sc_training_dataset_streams_valid_samples_and_compacts_labels(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sc.parquet"
    image = _image_bytes("red")
    pq.write_table(
        pa.table(
            {
                "sample_id": ["sample-a", "sample-b", "sample-c"],
                "label": ["a", "b", "c"],
                "patch_defective_bytes": [image, b"broken", image],
                "patch_template_bytes": [image, image, image],
            }
        ),
        path,
        row_group_size=1,
    )
    dataset = ScTrainingDataset(
        path,
        shuffle=False,
        seed=19,
        shuffle_buffer_rows=2,
    )

    summary = dataset.inspect(["a", "b", "c"])

    assert summary.active_labels == ("a", "c")
    assert summary.valid_samples == 2
    assert summary.skipped_unreadable_samples == 1
    assert len(dataset) == 2
    assert [sample.sample_id for sample in dataset] == ["sample-a", "sample-c"]


def test_sc_prediction_dataset_streams_missing_images_as_none(tmp_path: Path) -> None:
    path = tmp_path / "sc-prediction.parquet"
    image = _image_bytes("green")
    pq.write_table(
        pa.table(
            {
                "sample_id": ["sample-a", "sample-b"],
                "patch_defective_bytes": [image, None],
                "patch_template_bytes": [image, image],
            }
        ),
        path,
        row_group_size=1,
    )
    dataset = ScPredictionDataset(path)

    samples = list(dataset)

    assert len(dataset) == 2
    assert [sample.sample_id for sample in samples] == ["sample-a", "sample-b"]
    assert samples[0].defective_image == image
    assert samples[1].defective_image is None
    assert samples[1].reference_image == image


def test_open_hf_arrow_dataset_memory_maps_stream_without_side_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datasets = pytest.importorskip("datasets")
    cache_path = tmp_path / "hf-cache"
    monkeypatch.setattr(datasets.config, "HF_DATASETS_CACHE", str(cache_path))
    path = tmp_path / "materialized.arrow"
    table = _rows(6).append_column(
        ROW_INDEX_COLUMN,
        pa.array(range(6), type=pa.uint64()),
    )
    _write_arrow_stream(path, table)
    before = set(tmp_path.iterdir())

    dataset = open_hf_arrow_dataset(path, expected_schema=table.schema)

    assert dataset.cache_files == [{"filename": str(path.resolve())}]
    assert dataset[0] == {"value": 0, "text": "row-0", ROW_INDEX_COLUMN: 0}
    assert set(tmp_path.iterdir()) == before
    assert not cache_path.exists()


def test_open_hf_arrow_dataset_rejects_parquet_with_materialization_hint(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rows.parquet"
    _write_parquet(path, _rows(3))

    with pytest.raises(ValueError, match="preferred_format='arrow_ipc'"):
        open_hf_arrow_dataset(path)


def test_open_hf_arrow_dataset_rejects_ipc_file_container(tmp_path: Path) -> None:
    path = tmp_path / "file-container.arrow"
    table = _rows(3).append_column(ROW_INDEX_COLUMN, pa.array([0, 1, 2]))
    with pa.OSFile(str(path), "wb") as sink:
        with pa.ipc.new_file(sink, table.schema) as writer:
            writer.write_table(table)

    with pytest.raises(ValueError, match="new_stream"):
        open_hf_arrow_dataset(path)


def test_open_hf_arrow_dataset_requires_materialized_integer_index(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing-index.arrow"
    _write_arrow_stream(missing_path, _rows(3))
    with pytest.raises(ValueError, match=ROW_INDEX_COLUMN):
        open_hf_arrow_dataset(missing_path)

    string_path = tmp_path / "string-index.arrow"
    table = _rows(3).append_column(ROW_INDEX_COLUMN, pa.array(["a", "b", "c"]))
    _write_arrow_stream(string_path, table)
    with pytest.raises(ValueError, match="integer type"):
        open_hf_arrow_dataset(string_path)
