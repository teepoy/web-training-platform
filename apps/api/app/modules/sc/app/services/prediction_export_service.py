from __future__ import annotations

import asyncio
import json
import re
import tempfile
import zipfile
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import uuid4

import duckdb
import polars as pl
from klarf import (
    KlarfArray,
    KlarfBuilder,
    KlarfDocument,
    KlarfRecordBuilder,
    KlarfSymbol,
    dump,
)
from klarf.v12 import Klarf12Builder, dump12
from klarf.v12.models import Klarf12Document, Klarf12ImageList
from sampling_rules import (
    DuckDbSamplingSource,
    REVIEW_SAMPLING_RULE_CATALOG,
    ReviewSamplingProgram,
    compile_duckdb_review_sampling,
)

from app.modules.dataset_collections.port.local import CollectionExportReaderPort
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.sc.domain.prediction_export import (
    ScKlarfVersion,
    ScPredictionExportFormat,
    ScPredictionExportResult,
)
from app.modules.sc.domain.image_source import require_sc_image_source_format
from app.modules.sc.domain.job_image_source import ScJobImageSourceFactory
from app.modules.sc.runtime.streaming_prediction import (
    stream_sc_prediction_image_pairs,
)
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.api.schemas import Dataset, DatasetStorageMode
from app.shared.domain.protocols import ArtifactStorage

_KLARF_COLUMNS = (
    "DEFECTID",
    "XREL",
    "YREL",
    "XINDEX",
    "YINDEX",
    "XSIZE",
    "YSIZE",
    "DEFECTAREA",
    "DSIZE",
    "CLASSNUMBER",
    "TEST",
    "CLUSTERNUMBER",
    "ROUGHBINNUMBER",
    "FINEBINNUMBER",
    "REVIEWSAMPLE",
    "IMAGECOUNT",
    "IMAGELIST",
)
_KLARF_18_COLUMNS = (
    ("int32", "DEFECTID"),
    ("float", "XREL"),
    ("float", "YREL"),
    ("int32", "XINDEX"),
    ("int32", "YINDEX"),
    ("float", "XSIZE"),
    ("float", "YSIZE"),
    ("float", "DEFECTAREA"),
    ("float", "DSIZE"),
    ("int32", "CLASSNUMBER"),
    ("int32", "TEST"),
    ("int32", "CLUSTERNUMBER"),
    ("int32", "ROUGHBINNUMBER"),
    ("int32", "FINEBINNUMBER"),
    ("int32", "REVIEWSAMPLE"),
    ("ImageList", "IMAGEINFO"),
)
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_EXPORT_IMAGE_ROLE = "patch_defective"
_IMAGE_CONTENT_TYPES = {
    "image/jpeg": (".jpg", "JPEG"),
    "image/png": (".png", "PNG"),
    "image/tiff": (".tif", "TIFF"),
    "image/bmp": (".bmp", "BMP"),
}


@dataclass(frozen=True, slots=True)
class _ExportImage:
    sample_id: str
    archive_name: str
    local_path: Path
    klarf_format: str


class ScPredictionExportError(ValueError):
    pass


class ScPredictionExportService:
    def __init__(
        self,
        *,
        repository: DatasetRepository,
        collection_reader: CollectionExportReaderPort,
        storage_factory: DatasetStorageFactoryPort,
        artifact_storage: ArtifactStorage,
        image_source_factory: ScJobImageSourceFactory,
        image_batch_rows: int,
    ) -> None:
        if image_batch_rows <= 0:
            raise ValueError("image_batch_rows must be greater than zero")
        self._repository = repository
        self._collection_reader = collection_reader
        self._storage_factory = storage_factory
        self._artifact_storage = artifact_storage
        self._image_source_factory = image_source_factory
        self._image_batch_rows = image_batch_rows

    async def export(
        self,
        *,
        dataset_id: str,
        org_id: str,
        created_by: str,
        export_format: ScPredictionExportFormat,
        klarf_version: ScKlarfVersion = ScKlarfVersion.V1_2,
        sampling_program: ReviewSamplingProgram | None,
        sampling_seed: int | None,
        include_images: bool = False,
    ) -> ScPredictionExportResult:
        dataset = await self._repository.get_dataset(dataset_id, org_id=org_id)
        if dataset is None:
            raise ScPredictionExportError("Dataset not found")
        self._validate_dataset(dataset)
        if (sampling_program is None) != (sampling_seed is None):
            raise ScPredictionExportError(
                "Annotation Sampling program and seed must be provided together"
            )

        lazy_frame = await self._load_datasets((dataset,), org_id=org_id)
        image_source_formats = (
            {dataset.id: require_sc_image_source_format(dataset)}
            if include_images
            else {}
        )
        return await self._persist_export(
            org_id=org_id,
            scope_id=dataset.id,
            scope_kind="dataset",
            scope_name=dataset.name,
            source_dataset_ids=(dataset.id,),
            selected_member_ids=(),
            lazy_frame=lazy_frame,
            created_by=created_by,
            export_format=export_format,
            klarf_version=klarf_version,
            sampling_program=sampling_program,
            sampling_seed=sampling_seed,
            include_images=include_images,
            image_source_formats=image_source_formats,
        )

    async def export_collection(
        self,
        *,
        collection_id: str,
        member_ids: tuple[str, ...],
        org_id: str,
        created_by: str,
        export_format: ScPredictionExportFormat,
        klarf_version: ScKlarfVersion = ScKlarfVersion.V1_2,
        sampling_program: ReviewSamplingProgram | None,
        sampling_seed: int | None,
        include_images: bool = False,
    ) -> ScPredictionExportResult:
        if not member_ids:
            raise ScPredictionExportError(
                "Select at least one Collection record to export"
            )
        if len(member_ids) != len(set(member_ids)):
            raise ScPredictionExportError("Collection export member IDs must be unique")
        if (sampling_program is None) != (sampling_seed is None):
            raise ScPredictionExportError(
                "Annotation Sampling program and seed must be provided together"
            )

        collection = await self._collection_reader.get_collection(collection_id, org_id)
        members = await self._collection_reader.list_members(collection_id, org_id)
        member_by_id = {member.id: member for member in members}
        missing_member_ids = [
            member_id for member_id in member_ids if member_id not in member_by_id
        ]
        if missing_member_ids:
            raise ScPredictionExportError(
                "Selected Collection records are no longer linked: "
                + ", ".join(missing_member_ids)
            )
        dataset_ids = [
            member_by_id[member_id].source_dataset_id for member_id in member_ids
        ]
        datasets = await self._repository.list_datasets_by_ids(
            dataset_ids, org_id=org_id
        )
        dataset_by_id = {dataset.id: dataset for dataset in datasets}
        missing_dataset_ids = [
            dataset_id for dataset_id in dataset_ids if dataset_id not in dataset_by_id
        ]
        if missing_dataset_ids:
            raise ScPredictionExportError(
                "Selected Collection datasets are unavailable: "
                + ", ".join(missing_dataset_ids)
            )
        ordered_datasets = tuple(
            dataset_by_id[dataset_id] for dataset_id in dataset_ids
        )
        for dataset in ordered_datasets:
            self._validate_dataset(dataset)
        lazy_frame = await self._load_datasets(ordered_datasets, org_id=org_id)
        image_source_formats = (
            {
                dataset.id: require_sc_image_source_format(dataset)
                for dataset in ordered_datasets
            }
            if include_images
            else {}
        )
        return await self._persist_export(
            org_id=org_id,
            scope_id=collection.id,
            scope_kind="collection",
            scope_name=collection.name,
            source_dataset_ids=tuple(dataset_ids),
            selected_member_ids=member_ids,
            lazy_frame=lazy_frame,
            created_by=created_by,
            export_format=export_format,
            klarf_version=klarf_version,
            sampling_program=sampling_program,
            sampling_seed=sampling_seed,
            include_images=include_images,
            image_source_formats=image_source_formats,
        )

    async def _load_datasets(
        self,
        datasets: tuple[Dataset, ...],
        *,
        org_id: str,
    ) -> pl.LazyFrame:
        lazy_frames: list[pl.LazyFrame] = []
        for dataset in datasets:
            storage = await self._storage_factory.open(dataset.id, org_id)
            lazy_rows = await storage.list_samples(
                with_labels=True,
                with_predictions=True,
                return_lazyframe=True,
            )
            if not isinstance(lazy_rows, pl.LazyFrame):
                raise ScPredictionExportError(
                    "SC prediction export requires a bulk LazyFrame data source"
                )
            lazy_frames.append(
                lazy_rows.with_columns(
                    pl.lit(dataset.id).alias("source_dataset_id"),
                    pl.lit(dataset.name).alias("source_dataset_name"),
                )
            )
        combined = pl.concat(lazy_frames, how="diagonal_relaxed")
        return await asyncio.to_thread(_prepare_export_lazyframe, combined)

    async def _persist_export(
        self,
        *,
        org_id: str,
        scope_id: str,
        scope_kind: str,
        scope_name: str,
        source_dataset_ids: tuple[str, ...],
        selected_member_ids: tuple[str, ...],
        lazy_frame: pl.LazyFrame,
        created_by: str,
        export_format: ScPredictionExportFormat,
        klarf_version: ScKlarfVersion,
        sampling_program: ReviewSamplingProgram | None,
        sampling_seed: int | None,
        include_images: bool,
        image_source_formats: dict[str, str],
    ) -> ScPredictionExportResult:
        if include_images and export_format is ScPredictionExportFormat.PARQUET:
            raise ScPredictionExportError(
                "Defect images are available only for KLARF and ZIP exports"
            )
        created_at = datetime.now(timezone.utc)
        safe_name = _safe_filename(scope_name)
        export_id = str(uuid4())
        prefix = (
            f"exports/orgs/{org_id}/{scope_kind}s/{scope_id}/predictions/{export_id}"
        )
        sampled = sampling_program is not None

        with tempfile.TemporaryDirectory(prefix="sc-prediction-export-") as temp_dir:
            directory = Path(temp_dir)
            parquet_path = directory / f"{safe_name}_predictions.parquet"
            klarf_paths: list[Path] = []
            export_images: list[_ExportImage] = []
            frame: pl.DataFrame | None = None

            if (
                export_format is ScPredictionExportFormat.PARQUET
                and sampling_program is None
            ):
                row_count = await asyncio.to_thread(
                    _write_lazy_parquet,
                    lazy_frame,
                    parquet_path,
                )
            else:
                frame = await asyncio.to_thread(_collect_export_frame, lazy_frame)
                if sampling_program is not None:
                    assert sampling_seed is not None
                    frame = await asyncio.to_thread(
                        _apply_annotation_sampling,
                        frame,
                        sampling_program,
                        sampling_seed,
                    )
                row_count = frame.height
                klarf_frame = frame
                if include_images:
                    klarf_frame = frame.with_row_index("_export_image_index")
                    export_images = await self._resolve_export_images(
                        directory=directory,
                        frame=klarf_frame,
                        image_source_formats=image_source_formats,
                    )
                if export_format in (
                    ScPredictionExportFormat.PARQUET,
                    ScPredictionExportFormat.ZIP,
                ):
                    await asyncio.to_thread(_write_parquet, frame, parquet_path)
                if export_format in (
                    ScPredictionExportFormat.KLARF,
                    ScPredictionExportFormat.ZIP,
                ):
                    klarf_paths = await asyncio.to_thread(
                        _write_klarf_files,
                        directory,
                        klarf_frame,
                        created_at,
                        klarf_version,
                        tuple(export_images),
                    )

            manifest = {
                "contract": "sc.prediction-export.v2",
                "scope_kind": scope_kind,
                "scope_id": scope_id,
                "scope_name": scope_name,
                "source_dataset_ids": list(source_dataset_ids),
                "selected_collection_member_ids": list(selected_member_ids),
                "created_at": created_at.isoformat(),
                "created_by": created_by,
                "row_count": row_count,
                "inspection_count": len(klarf_paths),
                "annotation_sampling_applied": sampled,
                "annotation_sampling": _sampling_manifest(
                    sampling_program,
                    sampling_seed,
                ),
                "image_binaries_included": include_images,
                "image_count": len(export_images),
                "image_role": _EXPORT_IMAGE_ROLE if include_images else None,
                "klarf_version": (
                    klarf_version.value
                    if export_format
                    in (ScPredictionExportFormat.KLARF, ScPredictionExportFormat.ZIP)
                    else None
                ),
                "files": [
                    *(
                        [parquet_path.name]
                        if export_format
                        in (
                            ScPredictionExportFormat.PARQUET,
                            ScPredictionExportFormat.ZIP,
                        )
                        else []
                    ),
                    *(path.name for path in klarf_paths),
                ],
            }

            if export_format is ScPredictionExportFormat.PARQUET:
                path = parquet_path
                content_type = "application/vnd.apache.parquet"
            elif export_format is ScPredictionExportFormat.KLARF:
                if len(klarf_paths) == 1 and not include_images:
                    path = klarf_paths[0]
                    content_type = "text/plain; charset=utf-8"
                else:
                    path = directory / f"{safe_name}_predictions_klarf.zip"
                    await asyncio.to_thread(
                        _write_zip_package,
                        path,
                        (),
                        tuple(klarf_paths),
                        tuple(export_images),
                        manifest,
                    )
                    content_type = "application/zip"
            else:
                path = directory / f"{safe_name}_prediction_export.zip"
                await asyncio.to_thread(
                    _write_zip_package,
                    path,
                    (parquet_path,),
                    tuple(klarf_paths),
                    tuple(export_images),
                    manifest,
                )
                content_type = "application/zip"

            uri = await self._artifact_storage.put_file(
                f"{prefix}/{path.name}",
                str(path),
                content_type=content_type,
            )

        return ScPredictionExportResult(
            uri=uri,
            format=export_format,
            row_count=row_count,
            sampled=sampled,
            filename=path.name,
            klarf_version=(
                klarf_version
                if export_format
                in (ScPredictionExportFormat.KLARF, ScPredictionExportFormat.ZIP)
                else None
            ),
        )

    async def _resolve_export_images(
        self,
        *,
        directory: Path,
        frame: pl.DataFrame,
        image_source_formats: dict[str, str],
    ) -> list[_ExportImage]:
        images_directory = directory / "images"
        images_directory.mkdir()
        resolved_images: list[_ExportImage] = []
        async with self._image_source_factory.open() as image_resolver:
            resolved_stream = stream_sc_prediction_image_pairs(
                frame.lazy(),
                image_resolver=image_resolver,
                image_source_formats=image_source_formats,
                direct_dataset_id=None,
                input_batch_rows=self._image_batch_rows,
                roles=(_EXPORT_IMAGE_ROLE,),
            )
            async for index, item in _async_enumerate(resolved_stream):
                sample_id = str(item.get("sample_id") or "")
                error = item.get("error")
                if error:
                    raise ScPredictionExportError(
                        f"Unable to export defect image for sample {sample_id!r}: {error}"
                    )
                image_data = item.get(f"{_EXPORT_IMAGE_ROLE}_bytes")
                if not isinstance(image_data, bytes):
                    raise ScPredictionExportError(
                        f"Image resolver returned invalid bytes for sample {sample_id!r}"
                    )
                content_type = item.get(f"{_EXPORT_IMAGE_ROLE}_content_type")
                if not isinstance(content_type, str):
                    raise ScPredictionExportError(
                        f"Image resolver returned no content type for sample {sample_id!r}"
                    )
                image_type = _IMAGE_CONTENT_TYPES.get(content_type)
                if image_type is None:
                    raise ScPredictionExportError(
                        f"Unsupported defect image content type {content_type!r} for "
                        f"sample {sample_id!r}"
                    )
                extension, klarf_format = image_type
                archive_name = f"images/{index + 1:08d}{extension}"
                local_path = directory / archive_name
                await asyncio.to_thread(local_path.write_bytes, image_data)
                resolved_images.append(
                    _ExportImage(
                        sample_id=sample_id,
                        archive_name=archive_name,
                        local_path=local_path,
                        klarf_format=klarf_format,
                    )
                )
        if len(resolved_images) != frame.height:
            raise ScPredictionExportError(
                "Image resolver returned an incomplete export: "
                f"expected {frame.height}, got {len(resolved_images)}"
            )
        return resolved_images

    @staticmethod
    def _validate_dataset(dataset: Dataset) -> None:
        if dataset.dataset_type != "image_sc":
            raise ScPredictionExportError(
                "SC prediction export requires an image_sc dataset"
            )
        task_type = (
            dataset.task_spec.task_type if dataset.task_spec is not None else None
        )
        if task_type != "sc":
            raise ScPredictionExportError(
                "KLARF/Parquet prediction export is available only for SC datasets"
            )
        if dataset.storage_mode is not DatasetStorageMode.FILE_SHARD_SPARSE:
            raise ScPredictionExportError(
                "SC prediction export requires file_shard_sparse storage"
            )


def _safe_filename(value: str) -> str:
    normalized = _SAFE_FILENAME.sub("_", value.strip()).strip("._")
    return normalized or "dataset"


def _prepare_export_lazyframe(lazy_rows: object) -> pl.LazyFrame:
    if not isinstance(lazy_rows, pl.LazyFrame):
        raise ScPredictionExportError(
            "SC prediction export requires a bulk LazyFrame data source"
        )
    schema = lazy_rows.collect_schema()
    if "sample_id" not in schema:
        raise ScPredictionExportError("SC export rows are missing sample_id")

    defaults = {
        "inspection_time": pl.Utf8,
        "wafer_key": pl.Int64,
        "defect_id": pl.Int64,
        "wafer_x": pl.Float64,
        "wafer_y": pl.Float64,
        "index_x": pl.Int64,
        "index_y": pl.Int64,
        "size_x": pl.Float64,
        "size_y": pl.Float64,
        "size_d": pl.Float64,
        "area": pl.Float64,
        "class_number": pl.Int64,
        "test_id": pl.Int64,
        "cluster_id": pl.Int64,
        "repeater_id": pl.Int64,
        "rough_bin": pl.Int64,
        "final_bin": pl.Int64,
        "label": pl.Utf8,
        "predicted_label": pl.Utf8,
        "confidence": pl.Float64,
        "lot_id": pl.Utf8,
        "wafer_id": pl.Utf8,
        "device": pl.Utf8,
        "layer_id": pl.Utf8,
        "inspect_equip_id": pl.Utf8,
        "recipe_id": pl.Utf8,
        "center_x": pl.Float64,
        "center_y": pl.Float64,
        "origin_x": pl.Float64,
        "origin_y": pl.Float64,
        "die_size_x": pl.Float64,
        "die_size_y": pl.Float64,
    }
    missing = [
        pl.lit(None, dtype=dtype).alias(name)
        for name, dtype in defaults.items()
        if name not in schema
    ]
    if missing:
        lazy_rows = lazy_rows.with_columns(missing)

    return lazy_rows.with_columns(
        pl.col("sample_id").cast(pl.Utf8),
        pl.concat_str(
            [
                pl.col("source_dataset_id"),
                pl.lit(":"),
                pl.col("sample_id").cast(pl.Utf8),
            ]
        ).alias("export_row_id"),
        pl.when(
            pl.col("label").is_not_null()
            & ~pl.col("label").cast(pl.Utf8).is_in(["", "0"])
        )
        .then(pl.col("label").cast(pl.Utf8))
        .otherwise(pl.col("predicted_label").cast(pl.Utf8))
        .alias("final_class"),
    ).sort(["inspection_time", "wafer_key", "defect_id", "sample_id"])


def _collect_export_frame(lazy_rows: object) -> pl.DataFrame:
    if not isinstance(lazy_rows, pl.LazyFrame):
        raise ScPredictionExportError(
            "SC prediction export requires a bulk LazyFrame data source"
        )
    return lazy_rows.collect(engine="streaming")


def _apply_annotation_sampling(
    frame: pl.DataFrame,
    program: ReviewSamplingProgram,
    seed: int,
) -> pl.DataFrame:
    connection = duckdb.connect(":memory:")
    try:
        connection.register("samples", frame.to_arrow())
        compiled = compile_duckdb_review_sampling(
            DuckDbSamplingSource(
                sql="SELECT * FROM samples",
                parameters=(),
                identity_field="export_row_id",
                output_field="export_row_id",
            ),
            program=program,
            seed=seed,
        )
        selected = connection.execute(
            compiled.sql,
            list(compiled.parameters),
        ).to_arrow_table()
    finally:
        connection.close()
    selected_frame = cast(pl.DataFrame, pl.from_arrow(selected)).select(
        pl.col("export_row_id").cast(pl.Utf8)
    )
    return frame.join(selected_frame, on="export_row_id", how="semi")


def _write_parquet(frame: pl.DataFrame, path: Path) -> None:
    frame.write_parquet(path, compression="zstd", statistics=True)


def _write_lazy_parquet(frame: pl.LazyFrame, path: Path) -> int:
    frame.sink_parquet(
        path,
        compression="zstd",
        statistics=True,
        engine="streaming",
    )
    connection = duckdb.connect(":memory:")
    try:
        result = connection.execute(
            "SELECT count(*) FROM read_parquet(?)",
            [str(path)],
        ).fetchone()
    finally:
        connection.close()
    if result is None:
        raise ScPredictionExportError("Unable to count the exported Parquet rows")
    return int(result[0])


def _write_zip_package(
    path: Path,
    stored_paths: tuple[Path, ...],
    compressed_paths: tuple[Path, ...],
    images: tuple[_ExportImage, ...],
    manifest: dict[str, object],
) -> None:
    with zipfile.ZipFile(path, "w", allowZip64=True) as archive:
        # Parquet already uses Zstandard. Storing it avoids a costly second
        # compression pass while ZIP64 keeps packages above 4 GiB valid.
        for stored_path in stored_paths:
            archive.write(
                stored_path,
                stored_path.name,
                compress_type=zipfile.ZIP_STORED,
            )
        for compressed_path in compressed_paths:
            archive.write(
                compressed_path,
                compressed_path.name,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            )
        for image in images:
            archive.write(
                image.local_path,
                image.archive_name,
                compress_type=zipfile.ZIP_STORED,
            )
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
            compress_type=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        )


async def _async_enumerate(
    source: AsyncIterator[dict[str, object]],
) -> AsyncIterator[tuple[int, dict[str, object]]]:
    index = 0
    async for item in source:
        yield index, item
        index += 1


def _write_klarf_files(
    directory: Path,
    frame: pl.DataFrame,
    created_at: datetime,
    klarf_version: ScKlarfVersion,
    images: tuple[_ExportImage, ...],
) -> list[Path]:
    if frame.is_empty():
        raise ScPredictionExportError("KLARF export has no rows")
    if frame.get_column("inspection_time").null_count() > 0:
        raise ScPredictionExportError("KLARF export rows are missing inspection_time")
    if frame.get_column("wafer_key").null_count() > 0:
        raise ScPredictionExportError("KLARF export rows are missing wafer_key")

    partitions = frame.partition_by(
        ["inspection_time", "wafer_key"],
        maintain_order=True,
    )
    paths: list[Path] = []
    next_partition_by_name: dict[str, int] = {}
    for inspection_frame in partitions:
        filename_base = "-".join(
            _safe_filename(_single_required_text(inspection_frame, column))
            for column in ("layer_id", "lot_id", "wafer_id")
        )
        partition = next_partition_by_name.get(filename_base, 0)
        next_partition_by_name[filename_base] = partition + 1
        path = directory / f"{filename_base}.{partition:03d}"
        if klarf_version is ScKlarfVersion.V1_2:
            dump12(_build_klarf_document(inspection_frame, created_at, images), path)
        else:
            dump(_build_klarf_18_document(inspection_frame, created_at, images), path)
        paths.append(path)
    return paths


def _build_klarf_18_document(
    frame: pl.DataFrame,
    created_at: datetime,
    images: tuple[_ExportImage, ...] = (),
) -> KlarfDocument:
    defect_ids = _klarf_defect_ids(frame)
    rows = tuple(
        (
            defect_id,
            _required_number(row.get("wafer_x"), field="wafer_x"),
            _required_number(row.get("wafer_y"), field="wafer_y"),
            _required_integer(row.get("index_x"), field="index_x"),
            _required_integer(row.get("index_y"), field="index_y"),
            _required_number(row.get("size_x"), field="size_x"),
            _required_number(row.get("size_y"), field="size_y"),
            _required_number(row.get("area"), field="area"),
            _required_number(row.get("size_d"), field="size_d"),
            _required_integer(row.get("final_class"), field="Final Class"),
            _integer_or_default(row.get("test_id"), 1),
            _integer(row.get("cluster_id")),
            _integer(row.get("rough_bin")),
            _integer(row.get("final_bin")),
            1,
            _klarf_18_image_value(row, images),
        )
        for row, defect_id in zip(frame.iter_rows(named=True), defect_ids, strict=True)
    )
    inspection_time = _inspection_datetime(
        _single_required_value(frame, "inspection_time")
    )
    lot_id = _single_required_text(frame, "lot_id")
    wafer_id = _single_required_text(frame, "wafer_id")
    test_counts = (
        frame.with_columns(
            pl.col("test_id").fill_null(1).cast(pl.Int64, strict=False).fill_null(1)
        )
        .group_by("test_id")
        .len()
        .sort("test_id")
    )

    summary = KlarfRecordBuilder("SummaryRecord").add_list(
        "TestSummaryList",
        columns=(("int32", "TESTNO"), ("int32", "NDEFECT")),
        rows=tuple(
            (int(test_id), int(count)) for test_id, count in test_counts.iter_rows()
        ),
    )
    wafer = (
        KlarfRecordBuilder("WaferRecord", wafer_id)
        .add_field("SampleType", "WAFER")
        .add_field(
            "ResultTimestamp",
            inspection_time.strftime("%Y-%m-%d"),
            inspection_time.strftime("%H:%M:%S"),
        )
        .add_field(
            "SampleCenterLocation",
            _required_number(
                _single_required_value(frame, "center_x"), field="center_x"
            ),
            _required_number(
                _single_required_value(frame, "center_y"), field="center_y"
            ),
        )
        .add_field(
            "DiePitch",
            _required_number(
                _single_required_value(frame, "die_size_x"), field="die_size_x"
            ),
            _required_number(
                _single_required_value(frame, "die_size_y"), field="die_size_y"
            ),
        )
        .add_field(
            "DieOrigin",
            _required_number(
                _single_required_value(frame, "origin_x"), field="origin_x"
            ),
            _required_number(
                _single_required_value(frame, "origin_y"), field="origin_y"
            ),
        )
        .add_list("DefectList", columns=_KLARF_18_COLUMNS, rows=rows)
        .add_record(summary)
    )
    _add_optional_18_text_field(wafer, frame, "DeviceID", "device")
    _add_optional_18_text_field(wafer, frame, "StepID", "layer_id")
    _add_optional_18_text_field(wafer, frame, "InspectionStationID", "inspect_equip_id")
    _add_optional_18_text_field(wafer, frame, "RecipeID", "recipe_id")

    return (
        KlarfBuilder("1.8")
        .add_field(
            "FileTimestamp",
            created_at.strftime("%Y-%m-%d"),
            created_at.strftime("%H:%M:%S"),
        )
        .add_record(KlarfRecordBuilder("LotRecord", lot_id).add_record(wafer))
        .build()
    )


def _add_optional_18_text_field(
    builder: KlarfRecordBuilder,
    frame: pl.DataFrame,
    field_name: str,
    column: str,
) -> None:
    value = _single_optional_value(frame, column)
    if value is not None:
        builder.add_field(field_name, str(value))


def _build_klarf_document(
    frame: pl.DataFrame,
    created_at: datetime,
    images: tuple[_ExportImage, ...] = (),
) -> Klarf12Document:
    defect_ids = _klarf_defect_ids(frame)
    rows = [
        _klarf_row(
            row,
            export_defect_id=defect_id,
            image=_image_for_row(row, images),
        )
        for row, defect_id in zip(frame.iter_rows(named=True), defect_ids, strict=True)
    ]
    inspection_time = _inspection_datetime(
        _single_required_value(frame, "inspection_time")
    )
    lot_id = _single_required_text(frame, "lot_id")
    wafer_id = _single_required_text(frame, "wafer_id")
    builder = Klarf12Builder((1, 2))
    builder.add_record(
        "FileTimestamp",
        KlarfSymbol(created_at.strftime("%m-%d-%y")),
        KlarfSymbol(created_at.strftime("%H:%M:%S")),
    )
    builder.add_record(
        "ResultTimestamp",
        KlarfSymbol(inspection_time.strftime("%m-%d-%y")),
        KlarfSymbol(inspection_time.strftime("%H:%M:%S")),
    )
    builder.add_record("SampleType", KlarfSymbol("WAFER"))
    builder.add_record("LotID", lot_id)
    builder.add_record("WaferID", wafer_id)
    _add_optional_text_record(builder, frame, "DeviceID", "device")
    _add_optional_text_record(builder, frame, "StepID", "layer_id")
    _add_required_pair_record(
        builder,
        frame,
        "SampleCenterLocation",
        "center_x",
        "center_y",
    )
    _add_required_pair_record(builder, frame, "DiePitch", "die_size_x", "die_size_y")
    _add_required_pair_record(builder, frame, "DieOrigin", "origin_x", "origin_y")

    test_counts = (
        frame.with_columns(
            pl.col("test_id").fill_null(1).cast(pl.Int64, strict=False).fill_null(1)
        )
        .group_by("test_id")
        .len()
        .sort("test_id")
    )
    for test_id in test_counts.get_column("test_id").to_list():
        builder.add_record("InspectionTest", int(test_id))
    builder.add_schema("DefectRecordSpec", *_KLARF_COLUMNS)
    if images:
        for row, source_row in zip(
            rows,
            frame.iter_rows(named=True),
            strict=True,
        ):
            image = _image_for_row(source_row, images)
            if image is None:
                raise ScPredictionExportError(
                    "KLARF image export is missing an image reference"
                )
            builder.add_table(
                "DefectList",
                schema_name="DefectRecordSpec",
                rows=(row,),
            )
            builder.add_record("TiffFileName", KlarfSymbol(image.archive_name))
    else:
        builder.add_table("DefectList", schema_name="DefectRecordSpec", rows=rows)
    builder.add_schema("SummarySpec", "TESTNO", "NDEFECT")
    builder.add_table(
        "SummaryList",
        schema_name="SummarySpec",
        rows=tuple(
            (int(test_id), int(count)) for test_id, count in test_counts.iter_rows()
        ),
    )
    return builder.build()


def _klarf_row(
    row: dict[str, object],
    *,
    export_defect_id: int,
    image: _ExportImage | None = None,
) -> tuple[str | int | float | Klarf12ImageList, ...]:
    class_number = _required_integer(row.get("final_class"), field="Final Class")
    return (
        export_defect_id,
        _required_number(row.get("wafer_x"), field="wafer_x"),
        _required_number(row.get("wafer_y"), field="wafer_y"),
        _required_integer(row.get("index_x"), field="index_x"),
        _required_integer(row.get("index_y"), field="index_y"),
        _required_number(row.get("size_x"), field="size_x"),
        _required_number(row.get("size_y"), field="size_y"),
        _required_number(row.get("area"), field="area"),
        _required_number(row.get("size_d"), field="size_d"),
        class_number,
        _integer_or_default(row.get("test_id"), 1),
        _integer(row.get("cluster_id")),
        _integer(row.get("rough_bin")),
        _integer(row.get("final_bin")),
        1,
        1 if image is not None else 0,
        Klarf12ImageList(items=((1, 0),) if image is not None else ()),
    )


def _image_for_row(
    row: dict[str, object],
    images: tuple[_ExportImage, ...],
) -> _ExportImage | None:
    if not images:
        return None
    raw_index = row.get("_export_image_index")
    if isinstance(raw_index, bool) or not isinstance(raw_index, int):
        raise ScPredictionExportError(
            "KLARF image export row is missing its resolved image index"
        )
    try:
        return images[raw_index]
    except IndexError as exc:
        raise ScPredictionExportError(
            f"KLARF image export row references missing image index {raw_index}"
        ) from exc


def _klarf_18_image_value(
    row: dict[str, object],
    images: tuple[_ExportImage, ...],
) -> KlarfArray | KlarfSymbol:
    image = _image_for_row(row, images)
    if image is None:
        return KlarfSymbol("N")
    return KlarfArray(
        name="Images",
        items=((image.archive_name, image.klarf_format, 1, "Patch"),),
    )


def _klarf_defect_ids(frame: pl.DataFrame) -> list[int]:
    parsed: list[int] = []
    for value in frame.get_column("defect_id").to_list():
        try:
            parsed.append(int(str(value)))
        except (TypeError, ValueError):
            return list(range(1, frame.height + 1))
    if len(parsed) != len(set(parsed)):
        return list(range(1, frame.height + 1))
    return parsed


def _single_required_value(frame: pl.DataFrame, column: str) -> object:
    values = frame.get_column(column).drop_nulls().unique(maintain_order=True).to_list()
    if len(values) != 1:
        raise ScPredictionExportError(
            f"KLARF inspection requires one consistent {column}; found {len(values)}"
        )
    return values[0]


def _single_required_text(frame: pl.DataFrame, column: str) -> str:
    value = str(_single_required_value(frame, column)).strip()
    if not value:
        raise ScPredictionExportError(f"KLARF inspection is missing {column}")
    return value


def _single_optional_value(frame: pl.DataFrame, column: str) -> object | None:
    values = [
        value
        for value in frame.get_column(column)
        .drop_nulls()
        .unique(maintain_order=True)
        .to_list()
        if not isinstance(value, str) or value.strip()
    ]
    if not values:
        return None
    if len(values) != 1:
        raise ScPredictionExportError(
            f"KLARF inspection has conflicting {column} values"
        )
    return values[0]


def _add_optional_text_record(
    builder: Klarf12Builder,
    frame: pl.DataFrame,
    record_name: str,
    column: str,
) -> None:
    value = _single_optional_value(frame, column)
    if value is not None:
        builder.add_record(record_name, str(value))


def _add_required_pair_record(
    builder: Klarf12Builder,
    frame: pl.DataFrame,
    record_name: str,
    x_column: str,
    y_column: str,
) -> None:
    builder.add_record(
        record_name,
        _required_number(
            _single_required_value(frame, x_column),
            field=x_column,
        ),
        _required_number(
            _single_required_value(frame, y_column),
            field=y_column,
        ),
    )


def _inspection_datetime(value: object) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScPredictionExportError(
            f"Invalid KLARF inspection_time: {value!r}"
        ) from exc


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: object) -> int:
    return int(_number(value))


def _required_number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ScPredictionExportError(f"KLARF row is missing numeric {field}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ScPredictionExportError(
            f"KLARF row has invalid numeric {field}: {value!r}"
        ) from exc


def _required_integer(value: object, *, field: str) -> int:
    number = _required_number(value, field=field)
    if not number.is_integer():
        raise ScPredictionExportError(
            f"KLARF row requires integer {field}; got {value!r}"
        )
    return int(number)


def _integer_or_default(value: object, default: object) -> int:
    try:
        if value is not None and str(value).strip():
            return int(float(str(value)))
    except ValueError:
        pass
    return _integer(default)


def _sampling_manifest(
    program: ReviewSamplingProgram | None,
    seed: int | None,
) -> dict[str, object] | None:
    if program is None:
        return None
    if seed is None:
        raise ScPredictionExportError("Annotation Sampling seed is missing")
    rules: list[dict[str, object]] = []
    for rule in program.rules:
        descriptor = next(
            (
                candidate
                for candidate in REVIEW_SAMPLING_RULE_CATALOG
                if isinstance(rule, candidate.rule_type)
            ),
            None,
        )
        if descriptor is None:
            raise ScPredictionExportError(
                f"Unsupported Annotation Sampling rule: {type(rule).__name__}"
            )
        rules.append({"type": descriptor.id, **asdict(rule)})
    return {"seed": seed, "rules": rules}
