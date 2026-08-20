from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from typing import cast

import polars as pl

from app.modules.sc.app.services.prediction_export_service import (
    ScPredictionExportService,
)
from app.modules.dataset_collections.port.local import CollectionExportReaderPort
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.sc.domain.prediction_export import (
    ScKlarfVersion,
    ScPredictionExportFormat,
)
from app.modules.sc.domain.image_stream import ScExportImageStreamFactory
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.api.schemas import Dataset, DatasetStorageMode, TaskSpec
from app.shared.infrastructure.storage.minio import MinioArtifactStorage


@dataclass(frozen=True, slots=True)
class _Measurement:
    format: str
    samples: int
    seconds: float
    samples_per_second: float
    output_bytes: int


class _DatasetRepository:
    def __init__(self, dataset: Dataset) -> None:
        self._dataset = dataset

    async def get_dataset(
        self,
        dataset_id: str,
        *,
        org_id: str | None = None,
    ) -> Dataset | None:
        del org_id
        return self._dataset if dataset_id == self._dataset.id else None


class _DatasetStorage:
    def __init__(self, rows: pl.LazyFrame) -> None:
        self._rows = rows

    async def list_samples(
        self,
        *,
        with_labels: bool,
        with_predictions: bool,
        return_lazyframe: bool,
    ) -> pl.LazyFrame:
        if not (with_labels and with_predictions and return_lazyframe):
            raise AssertionError(
                "prediction export benchmark requires bulk current rows"
            )
        return self._rows


class _StorageFactory:
    def __init__(self, storage: _DatasetStorage) -> None:
        self._storage = storage

    async def open(self, dataset_id: str, org_id: str) -> _DatasetStorage:
        if dataset_id != "benchmark-dataset" or org_id != "benchmark-org":
            raise LookupError(dataset_id)
        return self._storage


class _UnusedCollectionReader:
    pass


class _UnusedImageSourceFactory:
    pass


def _benchmark_rows(samples: int) -> pl.LazyFrame:
    row = pl.int_range(0, samples, eager=True).alias("row_nr")
    return (
        pl.DataFrame(row)
        .with_columns(
            pl.concat_str(pl.lit("benchmark-"), pl.col("row_nr")).alias("sample_id"),
            pl.lit("2026-08-20T00:00:00").alias("inspection_time"),
            pl.lit(1).cast(pl.Int64).alias("wafer_key"),
            pl.col("row_nr").cast(pl.String).alias("defect_id"),
            (pl.col("row_nr") % 1000).cast(pl.Float64).alias("wafer_x"),
            (pl.col("row_nr") % 800).cast(pl.Float64).alias("wafer_y"),
            (pl.col("row_nr") % 50).cast(pl.Int64).alias("index_x"),
            ((pl.col("row_nr") / 50) % 50).cast(pl.Int64).alias("index_y"),
            pl.lit(3.0).alias("size_x"),
            pl.lit(4.0).alias("size_y"),
            pl.lit(5.0).alias("size_d"),
            pl.lit(12.0).alias("area"),
            pl.lit(10).cast(pl.Int64).alias("class_number"),
            pl.lit(1).cast(pl.Int64).alias("test_id"),
            pl.lit(0).cast(pl.Int64).alias("cluster_id"),
            pl.lit(0).cast(pl.Int64).alias("repeater_id"),
            pl.lit(1).cast(pl.Int64).alias("rough_bin"),
            pl.lit(2).cast(pl.Int64).alias("final_bin"),
            pl.lit(0).cast(pl.Int64).alias("images"),
            pl.when(pl.col("row_nr") % 5 == 0)
            .then(pl.lit("60"))
            .otherwise(pl.lit("0"))
            .alias("label"),
            pl.when(pl.col("row_nr") % 2 == 0)
            .then(pl.lit("40"))
            .otherwise(pl.lit("50"))
            .alias("predicted_label"),
            pl.lit(0.9).alias("confidence"),
            pl.lit("BENCH-LOT").alias("lot_id"),
            pl.lit("BENCH-WAFER").alias("wafer_id"),
            pl.lit("BENCH-DEVICE").alias("device"),
            pl.lit("BENCH-LAYER").alias("layer_id"),
            pl.lit("BENCH-EQUIP").alias("inspect_equip_id"),
            pl.lit("BENCH-RECIPE").alias("recipe_id"),
            pl.lit(1000).cast(pl.Int64).alias("center_x"),
            pl.lit(2000).cast(pl.Int64).alias("center_y"),
            pl.lit(10).cast(pl.Int64).alias("origin_x"),
            pl.lit(20).cast(pl.Int64).alias("origin_y"),
            pl.lit(800).cast(pl.Int64).alias("die_size_x"),
            pl.lit(500).cast(pl.Int64).alias("die_size_y"),
        )
        .drop("row_nr")
        .lazy()
    )


async def _run(args: argparse.Namespace) -> dict[str, object]:
    artifact_storage = MinioArtifactStorage(
        endpoint=args.minio_endpoint,
        access_key=args.minio_access_key,
        secret_key=args.minio_secret_key,
        bucket=args.minio_bucket,
        secure=False,
    )
    dataset = Dataset(
        id="benchmark-dataset",
        name="SC prediction export benchmark",
        dataset_type="image_sc",
        task_spec=TaskSpec(task_type="sc"),
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
    )
    service = ScPredictionExportService(
        repository=cast(DatasetRepository, _DatasetRepository(dataset)),
        collection_reader=cast(
            CollectionExportReaderPort,
            _UnusedCollectionReader(),
        ),
        storage_factory=cast(
            DatasetStorageFactoryPort,
            _StorageFactory(_DatasetStorage(_benchmark_rows(args.samples))),
        ),
        artifact_storage=artifact_storage,
        image_stream_factory=cast(
            ScExportImageStreamFactory,
            _UnusedImageSourceFactory(),
        ),
        image_batch_rows=512,
    )
    export_format = ScPredictionExportFormat(args.format)
    measurements: list[_Measurement] = []
    for _ in range(args.repeat):
        started = time.perf_counter()
        result = await service.export(
            dataset_id=dataset.id,
            org_id="benchmark-org",
            created_by="benchmark",
            export_format=export_format,
            klarf_version=ScKlarfVersion(args.klarf_version),
            sampling_program=None,
            sampling_seed=None,
        )
        elapsed = time.perf_counter() - started
        output_bytes = await artifact_storage.get_size(result.uri)
        measurements.append(
            _Measurement(
                format=export_format.value,
                samples=result.row_count,
                seconds=elapsed,
                samples_per_second=result.row_count / elapsed,
                output_bytes=output_bytes,
            )
        )
        await artifact_storage.delete(result.uri)

    seconds = [measurement.seconds for measurement in measurements]
    return {
        "samples": args.samples,
        "format": export_format.value,
        "klarf_version": args.klarf_version,
        "repeat": args.repeat,
        "median_seconds": statistics.median(seconds),
        "measurements": [asdict(measurement) for measurement in measurements],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark the complete SC prediction export and MinIO upload path."
    )
    parser.add_argument("--samples", type=int, default=300_000)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument(
        "--format",
        choices=[item.value for item in ScPredictionExportFormat],
        default=ScPredictionExportFormat.PARQUET.value,
    )
    parser.add_argument(
        "--klarf-version",
        choices=[item.value for item in ScKlarfVersion],
        default=ScKlarfVersion.V1_8.value,
    )
    parser.add_argument(
        "--minio-endpoint",
        default=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
    )
    parser.add_argument(
        "--minio-access-key",
        default=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
    )
    parser.add_argument(
        "--minio-secret-key",
        default=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
    )
    parser.add_argument(
        "--minio-bucket",
        default=os.environ.get("MINIO_BUCKET", "finetune-artifacts"),
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.samples <= 0 or args.repeat <= 0:
        raise SystemExit("--samples and --repeat must be greater than zero")
    print(json.dumps(asyncio.run(_run(args)), sort_keys=True))


if __name__ == "__main__":
    main()
