from __future__ import annotations

import io as _io
import json as _json
import random
import hashlib
import tempfile
import uuid as _uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, cast

import pyarrow as pa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.storage.domain.columnar_schemas import (
    SPARSE_EMBEDDED_IMAGE_STRUCT_DTYPE,
    SPARSE_MATERIALIZED_SCHEMA,
    SPARSE_PREDICTION_COLUMNS,
    SPARSE_PREDICTION_SCHEMA,
)
from app.modules.storage.domain.sparse import (
    DatasetPayloadStore,
    SparseAnnotationRecord,
    SparseAnnotationStore,
    SparseIndexReader,
    SparseManifestReader,
    build_annotation_record,
)
from app.modules.storage.domain.sparse.models import (
    ColumnSchema,
    DatasetManifest,
    SampleLocator,
    ShardEntry,
)

from app.modules.storage.adapter.sparse.import_operator import (
    SparseImportOperator,
)
from app.modules.datasets.domain.sample_row import (
    BulkSampleRow,
    PredictionResult,
    SampleRow,
    SampleRowImageRef,
)
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.storage.domain.storage_agg import MaterializeResult
from app.shared.api.schemas import (
    Annotation,
    Dataset,
    DatasetStorageMode,
    SampleFeature,
)
from app.shared.db.registry import SampleFeatureORM
from app.shared.domain.protocols import ArtifactStorage

_SCAN_PARQUET_SCHEMES = ("s3://", "file://")
_FINAL_PREDICTION_DIR = "final"
_ACCUMULATED_PREDICTION_FILE = "accumulated.parquet"
_CURRENT_PREDICTION_POINTER = "current.json"


# ---------------------------------------------------------------------------
# column type mapping for parquet schema construction
# ---------------------------------------------------------------------------

_SCALAR_TYPE_MAP: dict[str, pa.DataType] = {
    "string": pa.string(),
    "int32": pa.int32(),
    "int64": pa.int64(),
    "float32": pa.float32(),
    "float64": pa.float64(),
    "bool": pa.bool_(),
}


def _column_type_to_pa(type_name: str) -> pa.DataType:
    """Map a ColumnSchema type string to a PyArrow DataType."""
    dt = _SCALAR_TYPE_MAP.get(type_name)
    if dt is None:
        raise ValueError(f"Unknown ColumnSchema scalar type: {type_name}")
    return dt


class SparseDatasetStorage:
    """Dataset storage backed by object-storage Parquet shards (FILE_SHARD_SPARSE).

    All sample data lives in immutable parquet shards in object storage.
    Annotations are stored as append-only parquet sidecars via
    :class:`~app.modules.storage.domain.sparse.annotations.SparseAnnotationStore`.
    Implements the ``DatasetStorageAgg`` Protocol structurally (no
    inheritance).
    """

    _MODE: DatasetStorageMode = DatasetStorageMode.FILE_SHARD_SPARSE

    def __init__(
        self,
        dataset_id: str,
        org_id: str | None,
        dataset_metadata: Dataset,
        storage: ArtifactStorage,
        payload_store: DatasetPayloadStore,
        session_factory: async_sessionmaker,
        repo: DatasetRepository,
        prediction_compaction_memory_limit: str,
        prediction_compaction_temp_limit: str,
        prediction_compaction_row_group_rows: int,
        dataset_type: str = "",
    ) -> None:
        if prediction_compaction_row_group_rows <= 0:
            raise ValueError("prediction_compaction_row_group_rows must be positive")
        self._dataset_id: str = dataset_id
        self._org_id: str = org_id or ""
        self._dataset_metadata = dataset_metadata
        self._storage: ArtifactStorage = storage
        self._payload_store: DatasetPayloadStore = payload_store
        self._session_factory: async_sessionmaker = session_factory
        self._repo: DatasetRepository = repo
        self._reader: SparseManifestReader = SparseManifestReader()
        self._index_reader = SparseIndexReader()
        self._annotations: SparseAnnotationStore = SparseAnnotationStore(storage)
        self._dataset_type: str = dataset_type
        self._prediction_compaction_memory_limit = prediction_compaction_memory_limit
        self._prediction_compaction_temp_limit = prediction_compaction_temp_limit
        self._prediction_compaction_row_group_rows = (
            prediction_compaction_row_group_rows
        )

        # Lazy-loaded manifest cache.
        self._manifest: DatasetManifest | None = None

    # ── properties ──────────────────────────────────────────────────

    @property
    def dataset_id(self) -> str:
        return self._dataset_id

    @property
    def storage_mode(self) -> DatasetStorageMode:
        return self._MODE

    # ── metadata ────────────────────────────────────────────────────

    async def get_dataset_metadata(self) -> Any:
        """Return metadata already loaded while opening this storage instance."""
        return self._dataset_metadata

    # ── helpers ─────────────────────────────────────────────────────

    async def _get_manifest(self) -> DatasetManifest:
        """Load the sparse manifest, caching it for the lifetime of this instance."""
        if self._manifest is None:
            self._manifest = await self._payload_store.get_manifest(
                self._dataset_id, self._org_id
            )
        return self._manifest

    @staticmethod
    def _extract_sample_id(raw: dict[str, object]) -> str:
        """Extract the sample identity from a parquet row dict."""
        row_id = raw.get("id")
        if row_id is None:
            row_id = raw.get("sample_id")
        if row_id is None:
            raise ValueError("Row missing required 'id' or 'sample_id' column")
        return str(row_id)

    def _row_to_sample_row(
        self,
        row: dict[str, object],
        *,
        schema_version: str | None,
    ) -> SampleRow:
        """Convert a raw parquet row dict to a :class:`SampleRow`."""
        sample_id = self._extract_sample_id(row)

        if self._dataset_type == "image_sc":
            if schema_version in ("v3", "v4_identity"):
                return self._normalize_v3_row(row, sample_id)
            if schema_version == "v2":
                if "images" not in row:
                    raise ValueError("SC v2 shard row is missing its images column")
                return self._normalize_v2_row(row, sample_id)
            if schema_version not in (None, "v1"):
                raise ValueError(
                    f"Unsupported SC sparse schema version: {schema_version!r}"
                )

            # Legacy manifests did not persist a source schema version.  Keep
            # their historical column-based dispatch, but never use it for a
            # versioned manifest.
            if "images" in row:
                return self._normalize_v2_row(row, sample_id)
            return self._normalize_v1_row(row, sample_id)

        images_raw = row.get("images")
        if images_raw is not None:
            return self._normalize_v2_row(row, sample_id)

        return self._normalize_v1_row(row, sample_id)

    def _polars_storage_options(self) -> dict[str, str] | None:
        provider = getattr(self._storage, "polars_storage_options", None)
        if not callable(provider):
            return None
        options = provider()
        if not isinstance(options, dict):
            return None
        return {str(key): str(value) for key, value in options.items()}

    @staticmethod
    def _can_scan_parquet_uri(uri: str) -> bool:
        if uri.startswith(_SCAN_PARQUET_SCHEMES):
            return True
        return "://" not in uri

    def _scan_parquet_uris(self, uris: list[str]) -> Any | None:
        """Build a Polars LazyFrame directly over scan-capable parquet URIs."""
        import polars as pl

        parquet_uris = [uri for uri in uris if uri.endswith(".parquet")]
        if not parquet_uris or not all(
            self._can_scan_parquet_uri(uri) for uri in parquet_uris
        ):
            return None

        storage_options = self._polars_storage_options()
        if storage_options is None:
            return pl.scan_parquet(parquet_uris)
        return pl.scan_parquet(parquet_uris, storage_options=storage_options)

    async def _read_unscannable_parquet_uris(self, uris: list[str]) -> Any | None:
        """Read parquet bytes when the artifact URI cannot be scanned by Polars."""
        import polars as pl

        frames: list[pl.DataFrame] = []
        for uri in uris:
            if not uri.endswith(".parquet"):
                continue
            raw = await self._storage.get_bytes(uri)
            frames.append(pl.read_parquet(_io.BytesIO(raw)))
        if not frames:
            return None
        return pl.concat(frames, how="diagonal_relaxed").lazy()

    async def _parquet_uris_to_lazyframe(self, uris: list[str]) -> Any | None:
        lf = self._scan_parquet_uris(uris)
        if lf is not None:
            return lf
        return await self._read_unscannable_parquet_uris(uris)

    def _prediction_base_prefix(self) -> str:
        return f"datasets/{self._org_id}/{self._dataset_id}/predictions/"

    def _prediction_job_prefix(self, prediction_job_id: str) -> str:
        return f"{self._prediction_base_prefix()}{prediction_job_id}/"

    def _final_prediction_prefix(self) -> str:
        return f"{self._prediction_base_prefix()}{_FINAL_PREDICTION_DIR}/"

    async def _accumulated_prediction_uris(self) -> list[str]:
        uris = await self._storage.list_prefix(self._final_prediction_prefix())
        pointer_uri = next(
            (
                uri
                for uri in uris
                if uri.rsplit("/", 1)[-1] == _CURRENT_PREDICTION_POINTER
            ),
            None,
        )
        if pointer_uri is not None:
            payload = _json.loads(await self._storage.get_bytes(pointer_uri))
            current_uri = payload.get("snapshot_uri")
            if not isinstance(current_uri, str) or not current_uri:
                raise ValueError("prediction current pointer is missing snapshot_uri")
            return [current_uri]
        return [
            uri
            for uri in uris
            if uri.rsplit("/", 1)[-1] == _ACCUMULATED_PREDICTION_FILE
        ]

    async def _prediction_lazyframe(
        self, prediction_job_id: str | None = None
    ) -> Any | None:
        if prediction_job_id is None:
            uris = await self._accumulated_prediction_uris()
        else:
            uris = await self._storage.list_prefix(
                self._prediction_job_prefix(prediction_job_id)
            )
        if not uris:
            return None
        return await self._parquet_uris_to_lazyframe(uris)

    async def _annotation_history_lazyframe(self) -> Any | None:
        prefix = (
            self._annotations.get_annotations_prefix(self._dataset_id, self._org_id)
            + "/"
        )
        uris = await self._storage.list_prefix(prefix)
        return await self._parquet_uris_to_lazyframe(uris)

    async def _latest_annotation_lazyframe(self) -> Any | None:
        import polars as pl

        ann_lf = await self._annotation_history_lazyframe()
        if ann_lf is None:
            return None
        return (
            ann_lf.with_columns(
                pl.col("sample_id").cast(pl.Utf8),
                pl.col("created_at").cast(pl.Utf8),
            )
            .sort("created_at")
            .group_by("sample_id")
            .agg(
                pl.col("annotation_id").last().cast(pl.Utf8).alias("annotation_id"),
                pl.col("label").last().cast(pl.Utf8).alias("label"),
                pl.col("annotation_value")
                .last()
                .cast(pl.Utf8)
                .alias("annotation_value"),
                pl.col("created_by").last().cast(pl.Utf8).alias("created_by"),
                pl.col("created_at").last().cast(pl.Utf8).alias("created_at"),
                pl.col("user_id").last().cast(pl.Utf8).alias("user_id"),
            )
        )

    async def _latest_prediction_lazyframe(
        self, prediction_job_id: str | None = None
    ) -> Any | None:
        import polars as pl

        pred_lf = await self._prediction_lazyframe(prediction_job_id)
        if pred_lf is None:
            return None
        return (
            pred_lf.with_columns(pl.col("sample_id").cast(pl.Utf8))
            .group_by("sample_id")
            .agg(
                pl.col("predicted_label").last().cast(pl.Utf8).alias("predicted_label"),
                pl.col("confidence").last().cast(pl.Float64).alias("confidence"),
            )
        )

    async def annotation_overlay_lazyframe(self) -> tuple[Any | None, str]:
        prefix = (
            self._annotations.get_annotations_prefix(self._dataset_id, self._org_id)
            + "/"
        )
        uris = sorted(await self._storage.list_prefix(prefix))
        return await self._latest_annotation_lazyframe(), _fingerprint_uris(uris)

    async def prediction_overlay_lazyframe(self) -> tuple[Any | None, str]:
        uris = sorted(await self._accumulated_prediction_uris())
        return await self._latest_prediction_lazyframe(), _fingerprint_uris(uris)

    def _normalize_v1_row(self, row: dict[str, object], sample_id: str) -> SampleRow:
        """Normalize a v1 shard row (image_uris + scalar metadata columns)."""
        meta_raw = row.get("metadata", {})
        if isinstance(meta_raw, str):
            try:
                meta: dict[str, Any] = _json.loads(meta_raw) if meta_raw else {}
            except (ValueError, TypeError):
                meta = {}
        elif isinstance(meta_raw, dict):
            meta = dict(meta_raw)
        else:
            meta = {}

        for col, value in row.items():
            if col in ("id", "sample_id", "metadata"):
                continue
            if col == "image_uris" and isinstance(value, str):
                try:
                    meta.setdefault("image_uris", _json.loads(value) if value else [])
                except (ValueError, TypeError):
                    meta.setdefault("image_uris", [])
                continue
            meta.setdefault(col, value)

        image_uris_raw = row.get("image_uris", [])
        if isinstance(image_uris_raw, str):
            try:
                image_uris: list[str] = (
                    _json.loads(image_uris_raw) if image_uris_raw else []
                )
            except (ValueError, TypeError):
                image_uris = []
        elif isinstance(image_uris_raw, list):
            image_uris = [str(u) for u in image_uris_raw if u is not None]
        else:
            image_uris = []

        return SampleRow(
            sample_id=sample_id,
            dataset_id=self._dataset_id,
            image_uris=image_uris,
            metadata=meta,
        )

    def _normalize_v2_row(self, row: dict[str, object], sample_id: str) -> SampleRow:
        """Normalize a v2 shard row with embedded ``images`` column.

        Strips raw bytes from the row dict and returns structured image
        references with access URLs derived from sample identity.
        """
        images_list: list[dict[str, object]] = []
        raw = row.get("images")
        if isinstance(raw, list):
            images_list = [dict(img) if isinstance(img, dict) else {} for img in raw]

        image_uris: list[str] = []
        image_refs: list[SampleRowImageRef] = []
        for img in images_list:
            image_id = str(img.get("image_id", ""))
            if self._dataset_type == "image_sc":
                from app.modules.sc.domain.image_url import build_sc_image_url

                access_url = build_sc_image_url(
                    inspection_time=row.get("inspection_time"),
                    wafer_key=row.get("wafer_key"),
                    defect_id=row.get("defect_id") or sample_id,
                    image_type=img.get("image_type") or img.get("role"),
                    review_image_id=img.get("review_image_id"),
                )
            else:
                access_url = (
                    f"/api/v1/datasets/{self._dataset_id}/samples/"
                    f"{sample_id}/images/{image_id}"
                )
            image_uris.append(access_url)
            image_refs.append(
                SampleRowImageRef(
                    image_id=image_id,
                    role=str(img.get("role", "")),
                    content_type=str(img.get("content_type", "")),
                    filename=str(img.get("filename", "")),
                    bytes_=(
                        raw_bytes
                        if isinstance(raw_bytes := img.get("bytes"), bytes)
                        else None
                    ),
                    access_url=access_url,
                    image_type=str(img.get("image_type", "")),
                    review_image_id=(
                        rid
                        if isinstance(rid := img.get("review_image_id"), int)
                        else None
                    ),
                )
            )

        scalar_meta: dict[str, object] = {}
        for col, value in row.items():
            if col in ("id", "sample_id", "images"):
                continue
            scalar_meta[col] = value

        return SampleRow(
            sample_id=sample_id,
            dataset_id=self._dataset_id,
            image_uris=image_uris,
            images=image_refs if image_refs else None,
            metadata=scalar_meta,
        )

    def _normalize_v3_row(self, row: dict[str, object], sample_id: str) -> SampleRow:
        """Normalize a scalar-only SC row whose images resolve on demand."""
        scalar_meta = {
            col: value for col, value in row.items() if col not in ("id", "sample_id")
        }
        return SampleRow(
            sample_id=sample_id,
            dataset_id=self._dataset_id,
            image_uris=[],
            images=None,
            metadata=scalar_meta,
        )

    # ── shard navigation ────────────────────────────────────────────

    @staticmethod
    def _sorted_shard_ids(manifest: DatasetManifest, ids: list[str]) -> list[str]:
        """Return sample_ids sorted by (shard_index, row_index)."""

        def _natural_key(sid: str) -> tuple[int, int]:
            loc = manifest.sample_index.get(sid)
            if loc is None:
                return (0, 0)
            return (loc.shard_index, loc.row_index)

        return sorted(ids, key=_natural_key)

    async def _read_sample_from_locator(
        self, locator: SampleLocator, manifest: DatasetManifest
    ) -> dict[str, object] | None:
        """Read a single row given its locator and manifest."""
        if locator.shard_index < 0 or locator.shard_index >= len(manifest.shards):
            return None

        shard = manifest.shards[locator.shard_index]
        if locator.row_index < 0 or locator.row_index >= shard.row_count:
            return None

        rows = await self._reader.read_row_batch(
            shard.uri, locator.row_index, 1, self._storage
        )
        if not rows:
            return None
        return rows[0]

    async def _lookup_locators(
        self,
        manifest: DatasetManifest,
        sample_ids: list[str] | set[str],
    ) -> dict[str, SampleLocator]:
        if manifest.manifest_version == "v3":
            if manifest.index is None:
                if manifest.total_rows == 0:
                    return {}
                raise ValueError("manifest v3 is missing its sample index object")
            return await self._index_reader.lookup_many(
                manifest.index,
                sample_ids,
                dataset_id=self._dataset_id,
                storage=self._storage,
            )
        return {
            sample_id: locator
            for sample_id in sample_ids
            if (locator := manifest.sample_index.get(sample_id)) is not None
        }

    async def _all_sample_ids(self, manifest: DatasetManifest) -> list[str]:
        if manifest.manifest_version == "v3":
            if manifest.index is None:
                return []
            return await self._index_reader.all_sample_ids(
                manifest.index,
                storage=self._storage,
            )
        return list(manifest.sample_index)

    async def _read_manifest_page(
        self,
        manifest: DatasetManifest,
        *,
        offset: int,
        limit: int,
    ) -> list[dict[str, object]]:
        remaining_offset = offset
        remaining_limit = limit
        rows: list[dict[str, object]] = []
        for shard in sorted(manifest.shards, key=lambda item: item.shard_index):
            if remaining_limit <= 0:
                break
            if remaining_offset >= shard.row_count:
                remaining_offset -= shard.row_count
                continue
            take = min(shard.row_count - remaining_offset, remaining_limit)
            rows.extend(
                await self._reader.read_row_batch(
                    shard.uri,
                    remaining_offset,
                    take,
                    self._storage,
                )
            )
            remaining_limit -= take
            remaining_offset = 0
        return rows

    # ── list_samples ────────────────────────────────────────────────

    async def list_samples(
        self,
        offset: int = 0,
        limit: int = 50,
        *,
        with_labels: bool = False,
        with_predictions: bool = False,
        prediction_job_id: str | None = None,
        label_filter: str | None = None,
        order_by: str = "id",
        random_seed: int | None = None,
        sample_ids: list[str] | None = None,
        return_lazyframe: bool = False,
    ) -> tuple[list[Any], int] | Any:
        """Paginated sample listing over sparse parquet shards.

        Returns ``(list[SampleRow], total_count)`` unless
        *return_lazyframe* is True, in which case a ``pl.LazyFrame`` is
        returned.
        """
        # ── lazyframe fast-path ──────────────────────────────────
        if return_lazyframe:
            return await self._list_samples_lazyframe(
                with_labels=with_labels,
                with_predictions=with_predictions,
                prediction_job_id=prediction_job_id,
                sample_ids=sample_ids,
            )

        manifest = await self._get_manifest()

        direct_manifest_page = (
            sample_ids is None
            and label_filter is None
            and order_by == "id"
            and random_seed is None
        )
        if direct_manifest_page:
            raw_rows = await self._read_manifest_page(
                manifest,
                offset=offset,
                limit=limit,
            )
            page_ids = [self._extract_sample_id(row) for row in raw_rows]
            latest_by_sample: dict[str, Any] = {}
            if with_labels:
                latest_by_sample = await self._annotations.latest_by_sample_ids(
                    dataset_id=self._dataset_id,
                    org_id=self._org_id,
                    sample_ids=page_ids,
                )
            predictions_by_sample: dict[str, Any] = {}
            if with_predictions or prediction_job_id is not None:
                predictions_by_sample = await self._load_predictions(
                    prediction_job_id=prediction_job_id,
                    manifest=manifest,
                    sample_ids=page_ids,
                )
            return [
                self._enrich_sample_row(
                    self._row_to_sample_row(
                        raw_row,
                        schema_version=manifest.schema_version,
                    ),
                    latest_by_sample=latest_by_sample,
                    predictions_by_sample=predictions_by_sample,
                    with_labels=with_labels,
                    with_predictions=with_predictions,
                )
                for raw_row in raw_rows
            ], manifest.total_rows

        # ── resolve candidate sample_ids ─────────────────────────
        if sample_ids is not None:
            if len(sample_ids) == 0:
                return [], 0
            locators = await self._lookup_locators(manifest, sample_ids)
            all_sids = [sid for sid in sample_ids if sid in locators]
        else:
            all_sids = await self._all_sample_ids(manifest)
            locators = await self._lookup_locators(manifest, all_sids)

        # ── labels (load only for filter / order, not all rows) ──
        latest_by_sample: dict[str, Any] = {}
        if with_labels or label_filter is not None or order_by == "label":
            latest_by_sample = await self._annotations.latest_by_sample(
                dataset_id=self._dataset_id, org_id=self._org_id
            )

        # ── label filter ─────────────────────────────────────────
        if label_filter == "__unlabeled__":
            all_sids = [sid for sid in all_sids if sid not in latest_by_sample]
        elif label_filter == "__annotated__":
            all_sids = [sid for sid in all_sids if sid in latest_by_sample]
        elif label_filter is not None:
            all_sids = [
                sid
                for sid in all_sids
                if latest_by_sample.get(sid, {}).label == label_filter
            ]

        # ── ordering ─────────────────────────────────────────────
        if order_by == "label":

            def _label_key(sid: str) -> str:
                entry = latest_by_sample.get(sid)
                label = entry.label if entry is not None else ""
                return str(label) if label is not None else ""

            all_sids.sort(key=_label_key)
        elif order_by == "random" or random_seed is not None:
            rng = (
                random.Random(random_seed)
                if random_seed is not None
                else random.Random()
            )
            rng.shuffle(all_sids)
        else:
            # Natural order: by (shard_index, row_index)
            all_sids.sort(
                key=lambda sid: (
                    locators[sid].shard_index,
                    locators[sid].row_index,
                )
            )

        total = len(all_sids)

        # ── paginate ─────────────────────────────────────────────
        page_ids = all_sids[offset : offset + limit]

        # ── predictions ──────────────────────────────────────────
        predictions_by_sample: dict[str, Any] = {}
        if with_predictions or prediction_job_id is not None:
            predictions_by_sample = await self._load_predictions(
                prediction_job_id=prediction_job_id,
                manifest=manifest,
                sample_ids=page_ids,
            )

        # ── build SampleRow objects ──────────────────────────────
        result: list[SampleRow] = []
        for sid in page_ids:
            locator = locators.get(sid)
            if locator is None:
                continue

            raw_row = await self._read_sample_from_locator(locator, manifest)
            if raw_row is None:
                continue

            result.append(
                self._enrich_sample_row(
                    self._row_to_sample_row(
                        raw_row,
                        schema_version=manifest.schema_version,
                    ),
                    latest_by_sample=latest_by_sample,
                    predictions_by_sample=predictions_by_sample,
                    with_labels=with_labels,
                    with_predictions=with_predictions,
                )
            )

        return result, total

    @staticmethod
    def _enrich_sample_row(
        row: SampleRow,
        *,
        latest_by_sample: dict[str, Any],
        predictions_by_sample: dict[str, Any],
        with_labels: bool,
        with_predictions: bool,
    ) -> SampleRow:
        if (
            with_labels
            and (annotation := latest_by_sample.get(row.sample_id)) is not None
        ):
            row.latest_label = annotation.label
        if (
            with_predictions
            and (prediction := predictions_by_sample.get(row.sample_id)) is not None
        ):
            row.latest_prediction = {
                "predicted_label": prediction.get("predicted_label"),
                "confidence": prediction.get("confidence"),
                "all_scores": prediction.get("all_scores"),
                "model_id": prediction.get("model_id"),
                "target": prediction.get("target"),
                "model_version": prediction.get("model_version"),
                "job_id": prediction.get("job_id"),
                "error": prediction.get("error"),
            }
        return row

    async def _list_samples_lazyframe(
        self,
        *,
        with_labels: bool = False,
        with_predictions: bool = False,
        prediction_job_id: str | None = None,
        sample_ids: list[str] | None = None,
    ) -> Any:
        """Return a ``pl.LazyFrame`` over all sample shards.

        For object storage backends, this constructs a native Polars
        ``scan_parquet`` over all sample shard URIs and passes through
        backend credentials via ``storage_options``.

        When *with_labels* is True, loads annotations from
        annotation parquet sidecars and resolves latest-per-sample with
        Polars before joining. Prediction columns follow the same pattern.
        """
        import polars as pl

        manifest = await self._get_manifest()
        shards = sorted(manifest.shards, key=lambda s: s.shard_index)
        shard_uris = [shard.uri for shard in shards if shard.row_count > 0]

        lf = await self._parquet_uris_to_lazyframe(shard_uris)
        if lf is None:
            lf = pl.DataFrame({"sample_id": []}, schema={"sample_id": pl.Utf8}).lazy()

        schema_names = set(lf.collect_schema().names())
        if "sample_id" in schema_names:
            lf = lf.with_columns(pl.col("sample_id").cast(pl.Utf8))
        elif "id" in schema_names:
            lf = lf.with_columns(pl.col("id").cast(pl.Utf8).alias("sample_id"))
        else:
            lf = lf.with_columns(pl.lit(None, dtype=pl.Utf8).alias("sample_id"))

        sample_id_filter = (
            [str(sid) for sid in sample_ids] if sample_ids is not None else None
        )

        if with_labels:
            ann_lf = await self._latest_annotation_lazyframe()
            if ann_lf is None:
                lf = lf.with_columns(
                    pl.lit(None, dtype=pl.Utf8).alias("label"),
                    pl.lit(None, dtype=pl.Utf8).alias("annotation_value"),
                )
            else:
                lf = lf.join(ann_lf, on="sample_id", how="left")

        if with_predictions:
            pred_lf = await self._latest_prediction_lazyframe(prediction_job_id)
            if pred_lf is None:
                lf = lf.with_columns(
                    pl.lit(None, dtype=pl.Utf8).alias("predicted_label")
                )
            else:
                lf = lf.join(pred_lf, on="sample_id", how="left")

        if sample_id_filter is not None:
            lf = (
                lf.filter(pl.col("sample_id").is_in(sample_id_filter))
                if sample_id_filter
                else lf.filter(pl.lit(False))
            )

        return lf

    async def update_sample_image_uris(
        self, sample_id: str, image_uris: list[str]
    ) -> SampleRow | None:
        raise NotImplementedError("sparse datasets do not support image upload")

    async def _load_predictions(
        self,
        *,
        prediction_job_id: str | None,
        manifest: DatasetManifest,
        sample_ids: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Load prediction results, optionally filtered by job_id.

        Job-scoped predictions are stored as per-job parquet files under
        ``datasets/{org_id}/{dataset_id}/predictions/{job_id}/``. Unscoped
        latest predictions are read from the accumulated final parquet.
        """
        import pyarrow.parquet as pq

        del manifest

        if prediction_job_id is None:
            uris = await self._accumulated_prediction_uris()
        else:
            uris = await self._storage.list_prefix(
                self._prediction_job_prefix(prediction_job_id)
            )

        filters = (
            [("sample_id", "in", sorted(set(sample_ids)))]
            if sample_ids is not None and sample_ids
            else None
        )
        results: dict[str, dict[str, Any]] = {}
        for uri in uris:
            if not uri.endswith(".parquet"):
                continue
            raw = await self._storage.get_bytes(uri)
            table = pq.read_table(_io.BytesIO(raw), filters=filters)
            rows = table.to_pylist()
            for row in rows:
                sid = str(row.get("sample_id", ""))
                if sid:
                    all_scores = row.get("all_scores")
                    if isinstance(all_scores, str):
                        all_scores = _json.loads(all_scores)
                    results[sid] = {
                        "predicted_label": str(row.get("predicted_label", "")),
                        "confidence": row.get("confidence"),
                        "all_scores": all_scores,
                        "model_id": str(row.get("model_id", "")),
                        "target": str(row.get("target", "")),
                        "model_version": row.get("model_version"),
                        "job_id": str(row.get("job_id", "")),
                        "error": row.get("error"),
                    }

        return results

    # ── get_sample ──────────────────────────────────────────────────

    async def get_sample(self, sample_id: str) -> SampleRow | None:
        """Look up a single sample by id via the manifest sample_index."""
        manifest = await self._get_manifest()
        locator = (await self._lookup_locators(manifest, [sample_id])).get(sample_id)
        if locator is None:
            return None

        raw_row = await self._read_sample_from_locator(locator, manifest)
        if raw_row is None:
            return None

        return self._row_to_sample_row(
            raw_row,
            schema_version=manifest.schema_version,
        )

    # ── get_samples_by_id ───────────────────────────────────────────

    async def get_samples_by_id(
        self,
        sample_ids: list[str],
    ) -> dict[str, SampleRow]:
        """Batch-lookup samples, grouping reads by shard for efficiency."""
        if not sample_ids:
            return {}

        manifest = await self._get_manifest()

        locators = await self._lookup_locators(manifest, sample_ids)

        # Group sample_ids by shard_index
        by_shard: dict[int, list[tuple[str, int]]] = {}
        for sid in sample_ids:
            locator = locators.get(sid)
            if locator is not None:
                by_shard.setdefault(locator.shard_index, []).append(
                    (sid, locator.row_index)
                )

        # Read each shard once, extract all requested rows
        shard_rows: dict[str, dict[str, object]] = {}
        for shard_index, items in by_shard.items():
            if shard_index < 0 or shard_index >= len(manifest.shards):
                continue
            shard = manifest.shards[shard_index]

            valid_items = [
                (sid, row_index)
                for sid, row_index in items
                if 0 <= row_index < shard.row_count
            ]
            rows_by_index = await self._reader.read_rows(
                shard.uri,
                [row_index for _, row_index in valid_items],
                self._storage,
            )
            for sid, row_index in valid_items:
                raw = rows_by_index.get(row_index)
                if raw is not None:
                    shard_rows[sid] = raw

        return {
            sid: self._row_to_sample_row(
                raw,
                schema_version=manifest.schema_version,
            )
            for sid in sample_ids
            if (raw := shard_rows.get(sid)) is not None
        }

    async def existing_sample_ids(self, sample_ids: set[str]) -> set[str]:
        if not sample_ids:
            return set()
        manifest = await self._get_manifest()
        return set(await self._lookup_locators(manifest, sample_ids))

    async def map_upstream_item_ids_to_sample_ids(
        self, upstream_item_ids: set[str]
    ) -> dict[str, str]:
        if not upstream_item_ids:
            return {}
        manifest = await self._get_manifest()
        if manifest.manifest_version == "v3":
            if manifest.index is None:
                if manifest.total_rows == 0:
                    return {}
                raise ValueError("manifest v3 is missing its sample index object")
            return await self._index_reader.lookup_by_upstream_item_ids(
                manifest.index,
                upstream_item_ids,
                storage=self._storage,
            )

        wanted = {str(item_id) for item_id in upstream_item_ids}
        result: dict[str, str] = {}
        for sample_id, locator in manifest.sample_index.items():
            if locator.upstream_item_id is None:
                continue
            upstream_key = str(locator.upstream_item_id)
            if upstream_key not in wanted:
                continue
            existing = result.get(upstream_key)
            if existing is not None and existing != sample_id:
                raise ValueError(
                    "sparse index contains duplicate upstream item identity: "
                    f"{upstream_key}"
                )
            result[upstream_key] = str(sample_id)
        return result

    # ── write_samples ───────────────────────────────────────────────

    async def write_samples(
        self,
        rows: AsyncIterator[BulkSampleRow],
        *,
        schema_columns: list[ColumnSchema] | None = None,
        batch_size: int = 1000,
    ) -> int:
        """Streaming batch write of BulkSampleRow objects to parquet shards.

        Accumulates batches, converts each BulkSampleRow to a dict,
        writes parquet shards via :class:`SparseImportOperator`, and
        finalises the dataset manifest after all batches are flushed.
        """
        operator = SparseImportOperator(
            dataset_id=self._dataset_id,
            org_id=self._org_id,
            payload_store=self._payload_store,
        )

        pyarrow_schema = self._build_write_schema(schema_columns)

        batch: list[BulkSampleRow] = []
        shard_entries: list[ShardEntry] = []
        sample_index: dict[str, SampleLocator] = {}
        try:
            existing_manifest = await self._get_manifest()
        except FileNotFoundError:
            existing_manifest = DatasetManifest(
                dataset_id=self._dataset_id,
                storage_mode=self._MODE.value,
                shard_count=0,
                total_rows=0,
                schema_columns=schema_columns or [],
                shards=[],
                sample_index={},
                schema_version="v2",
            )

        if existing_manifest.manifest_version == "v3" and existing_manifest.total_rows:
            raise NotImplementedError(
                "appending samples to manifest-v3 sparse datasets requires an "
                "explicit index merge operation"
            )

        shard_idx = len(existing_manifest.shards)
        total = 0

        async for row in rows:
            batch.append(row)
            if len(batch) >= batch_size:
                n, entry, locs = await self._write_shard_batch(
                    operator, batch, pyarrow_schema, shard_idx
                )
                shard_entries.append(entry)
                sample_index.update(locs)
                shard_idx += 1
                total += n
                batch = []

        # Flush remaining rows
        if batch:
            n, entry, locs = await self._write_shard_batch(
                operator, batch, pyarrow_schema, shard_idx
            )
            shard_entries.append(entry)
            sample_index.update(locs)
            total += n

        if shard_entries:
            duplicate_ids = set(existing_manifest.sample_index).intersection(
                sample_index
            )
            if duplicate_ids:
                raise ValueError(
                    "Duplicate sample ids while appending sparse samples: "
                    + ", ".join(sorted(duplicate_ids)[:10])
                )

            merged_shards = [*existing_manifest.shards, *shard_entries]
            merged_sample_index = {
                **existing_manifest.sample_index,
                **sample_index,
            }
            merged_total = existing_manifest.total_rows + total
            await operator.finalize_manifest(
                shard_entries=merged_shards,
                sample_index=merged_sample_index,
                total_rows=merged_total,
                shard_count=len(merged_shards),
                schema_columns=schema_columns or [],
                schema_version="v2",
            )
            # Invalidate cached manifest so next read picks up the new data
            self._manifest = None
            self._payload_store.invalidate_manifest(self._dataset_id, self._org_id)

        return total

    # ── write_samples helpers ──────────────────────────────────────

    @staticmethod
    def _build_write_schema(
        schema_columns: list[ColumnSchema] | None,
    ) -> pa.Schema:
        fields = [
            pa.field("id", pa.string(), nullable=False),
            pa.field("sample_id", pa.string(), nullable=False),
            pa.field(
                "images",
                pa.list_(SPARSE_EMBEDDED_IMAGE_STRUCT_DTYPE),
                nullable=False,
            ),
        ]

        if schema_columns:
            for col in schema_columns:
                fields.append(pa.field(col.name, _column_type_to_pa(col.type)))

        return pa.schema(fields)

    async def _write_shard_batch(
        self,
        operator: SparseImportOperator,
        rows: list[BulkSampleRow],
        pyarrow_schema: pa.Schema,
        shard_index: int,
    ) -> tuple[int, ShardEntry, dict[str, SampleLocator]]:
        """Convert a BulkSampleRow batch to dicts and flush to storage."""
        dict_rows: list[dict[str, Any]] = []
        for row in rows:
            d: dict[str, Any] = {
                "id": row.sample_id,
                "sample_id": row.sample_id,
            }
            # Embedded images (v2)
            if row.images:
                d["images"] = [
                    {
                        "image_id": img.image_id,
                        "image_type": img.image_type,
                        "role": img.role,
                        "content_type": img.content_type,
                        "filename": img.filename,
                        "bytes": img.bytes_,
                        "review_image_id": img.review_image_id,
                        "source_uri": img.source_uri,
                    }
                    for img in row.images
                ]
            else:
                d["images"] = []

            # Extra metadata columns (schema_columns beyond the core set)
            for key, value in row.extra.items():
                d.setdefault(key, value)
            for key, value in row.metadata.items():
                d.setdefault(key, value)

            dict_rows.append(d)

        entry, locators = await operator.flush_shard(
            shard_index=shard_index,
            rows=dict_rows,
            pyarrow_schema=pyarrow_schema,
            row_id_key="sample_id",
        )
        return len(rows), entry, locators

    # ── create_annotations ──────────────────────────────────────────

    async def create_annotations(self, annotations: list[Annotation]) -> int:
        """Batch write annotations to the sparse annotation sidecar.

        Each :class:`~app.shared.api.schemas.Annotation` is converted to
        a :class:`~app.modules.storage.domain.sparse.SparseAnnotationRecord` and
        appended to the immutable parquet sidecar.
        """
        if not annotations:
            return 0

        records: list[SparseAnnotationRecord] = []
        for a in annotations:
            records.append(
                build_annotation_record(
                    sample_id=a.sample_id,
                    label=a.label,
                    annotation_value=(
                        _json.dumps(a.annotation_value)
                        if a.annotation_value is not None
                        else ""
                    ),
                    created_by=a.created_by,
                    created_at=a.created_at,
                )
            )

        await self._annotations.append(
            dataset_id=self._dataset_id,
            org_id=self._org_id,
            items=records,
        )
        return len(records)

    # ── update_annotations ──────────────────────────────────────────

    async def update_annotations(self, updates: list[tuple[str, str]]) -> int:
        """Update annotation labels by appending updated records.

        Each update is ``(annotation_id, new_label)``.  Loads existing
        records to discover the corresponding ``sample_id``, then appends
        new records with a fresh ``created_at`` so that
        ``latest_by_sample()`` surfaces the update.

        Uses the append-only pattern — old records are not deleted from
        the sidecar, merely superseded by newer timestamps.
        """
        if not updates:
            return 0

        update_map = dict(updates)
        id_to_rec = await self._annotations.records_by_annotation_ids(
            dataset_id=self._dataset_id,
            org_id=self._org_id,
            annotation_ids=set(update_map),
        )

        new_records: list[SparseAnnotationRecord] = []
        for ann_id, new_label in update_map.items():
            prev = id_to_rec.get(ann_id)
            if prev is None:
                continue
            new_records.append(
                build_annotation_record(
                    sample_id=prev.sample_id,
                    label=new_label,
                    annotation_value=prev.annotation_value,
                    created_by=prev.created_by,
                    user_id=prev.user_id,
                    created_at=datetime.now(timezone.utc),
                )
            )

        if not new_records:
            return 0

        await self._annotations.append(
            dataset_id=self._dataset_id,
            org_id=self._org_id,
            items=new_records,
        )
        return len(new_records)

    # ── delete_annotations ──────────────────────────────────────────

    async def delete_annotations(self, annotation_ids: list[str]) -> int:
        """Delete annotations via append-only compaction.

        Loads all existing records, filters out those with the given
        *annotation_ids*, computes latest-per-sample from the remainder,
        and appends a consolidated pack with fresh timestamps.  Newer
        timestamps ensure ``latest_by_sample()`` ignores the old records.

        This is a full sidecar read + rewrite and is appropriate for
        occasional manual corrections, not bulk operations.
        """
        if not annotation_ids:
            return 0

        doomed: set[str] = set(annotation_ids)
        existing_by_id = await self._annotations.records_by_annotation_ids(
            dataset_id=self._dataset_id,
            org_id=self._org_id,
            annotation_ids=doomed,
        )
        deleted_records = list(existing_by_id.values())
        deleted_count = len(deleted_records)
        if deleted_count == 0:
            return 0

        tombstones: list[SparseAnnotationRecord] = []
        now = datetime.now(timezone.utc).isoformat()
        for sample_id in {r.sample_id for r in deleted_records}:
            tombstones.append(
                SparseAnnotationRecord(
                    annotation_id=f"deleted:{sample_id}:{now}",
                    sample_id=sample_id,
                    label="",
                    annotation_value="",
                    created_by="",
                    created_at=now,
                    user_id="",
                )
            )
        await self._annotations.append(
            dataset_id=self._dataset_id,
            org_id=self._org_id,
            items=tombstones,
        )

        return deleted_count

    # ── get_annotation_stats ────────────────────────────────────────

    async def get_annotation_stats(self) -> dict[str, Any]:
        """Return the storage-aggregate annotation statistics contract."""
        import polars as pl

        latest = await self._latest_annotation_lazyframe()
        if latest is None:
            label_counts: dict[str, int] = {}
        else:
            stats = await (
                latest.filter(pl.col("label").is_not_null() & (pl.col("label") != ""))
                .group_by("label")
                .len()
                .collect_async(engine="streaming")
            )
            label_counts = {
                str(row["label"]): int(row["len"]) for row in stats.to_dicts()
            }
        manifest = await self._get_manifest()
        annotated_samples = sum(label_counts.values())
        return {
            "total_samples": manifest.total_rows,
            "annotated_samples": annotated_samples,
            "unlabeled_samples": max(manifest.total_rows - annotated_samples, 0),
            "label_counts": label_counts,
        }

    async def metadata_histogram(self, key: str) -> dict:
        """Return value counts for a metadata column or struct field."""
        import polars as pl

        lf = cast(Any, await self.list_samples(return_lazyframe=True))
        schema = lf.collect_schema()
        names = set(schema.names())
        if key in names:
            value_expr = pl.col(key)
        elif "metadata" in names and isinstance(schema["metadata"], pl.Struct):
            value_expr = pl.col("metadata").struct.field(key)
        else:
            return {"key": key, "histogram": [], "total_non_null": 0}

        hist_df = (
            lf.select(value_expr.alias("value"))
            .filter(pl.col("value").is_not_null())
            .group_by("value")
            .len()
            .rename({"len": "count"})
            .sort("count", descending=True)
            .limit(200)
            .collect()
        )

        histogram = hist_df.to_dicts()
        return {
            "key": key,
            "histogram": histogram,
            "total_non_null": sum(int(row["count"]) for row in histogram),
        }

    async def wafer_points(self) -> dict:
        """Return wafer point coordinates derived from sparse sample columns."""
        import polars as pl

        lf = cast(Any, await self.list_samples(return_lazyframe=True))
        schema = lf.collect_schema()
        names = set(schema.names())
        id_expr = pl.col("sample_id") if "sample_id" in names else pl.col("id")

        if "x" in names and "y" in names:
            x_expr = pl.col("x")
            y_expr = pl.col("y")
        elif "metadata" in names and isinstance(schema["metadata"], pl.Struct):
            x_expr = pl.col("metadata").struct.field("x")
            y_expr = pl.col("metadata").struct.field("y")
        else:
            return {"points": [], "total": 0}

        points_df = lf.select(
            id_expr.cast(pl.Utf8).alias("id"),
            x_expr.cast(pl.Float64, strict=False).fill_null(0.0).alias("x"),
            y_expr.cast(pl.Float64, strict=False).fill_null(0.0).alias("y"),
        ).collect()

        points = points_df.to_dicts()
        return {"points": points, "total": len(points)}

    # ── list_annotations ───────────────────────────────────────────

    async def list_annotations(
        self,
        *,
        sample_id: str | None = None,
        dataset_id: str | None = None,
        limit: int | None = None,
    ) -> list[Annotation]:
        import polars as pl

        latest = await self._latest_annotation_lazyframe()
        if latest is None:
            return []
        if sample_id:
            latest = latest.filter(pl.col("sample_id") == sample_id)
        latest = latest.filter(
            pl.col("label").is_not_null() & (pl.col("label") != "")
        ).sort("created_at", descending=True)
        if limit is not None:
            latest = latest.limit(limit)
        frame = await latest.collect_async(engine="streaming")
        return [_annotation_from_sparse_row(row) for row in frame.to_dicts()]

    # ── list_annotations_by_sample_ids ──────────────────────────────

    async def list_annotations_by_sample_ids(
        self, sample_ids: list[str]
    ) -> list[Annotation]:
        if not sample_ids:
            return []
        import polars as pl

        latest = await self._latest_annotation_lazyframe()
        if latest is None:
            return []
        frame = await latest.filter(
            pl.col("sample_id").is_in(sample_ids)
            & pl.col("label").is_not_null()
            & (pl.col("label") != "")
        ).collect_async(engine="streaming")
        return [_annotation_from_sparse_row(row) for row in frame.to_dicts()]

    async def get_annotations_batch(
        self, annotation_ids: list[str]
    ) -> list[Annotation]:
        if not annotation_ids:
            return []
        records = await self._annotations.records_by_annotation_ids(
            dataset_id=self._dataset_id,
            org_id=self._org_id,
            annotation_ids=annotation_ids,
        )
        by_id = {
            annotation_id: _annotation_from_sparse_record(record)
            for annotation_id, record in records.items()
        }
        return [
            by_id[annotation_id]
            for annotation_id in annotation_ids
            if annotation_id in by_id
        ]

    # ── replace_annotations_for_samples ─────────────────────────────

    async def replace_annotations_for_samples(
        self, items: list[tuple[str, str | None]], *, created_by: str = ""
    ) -> int:
        if not items:
            return 0
        seen: dict[str, str | None] = {}
        for sample_id, label in items:
            seen[sample_id] = label

        records: list[SparseAnnotationRecord] = []
        for sample_id, label in seen.items():
            records.append(
                build_annotation_record(
                    sample_id=sample_id,
                    label=label if label is not None else "",
                    created_by=created_by,
                )
            )
        await self._annotations.append(
            dataset_id=self._dataset_id,
            org_id=self._org_id,
            items=records,
        )
        return sum(1 for label in seen.values() if label is not None)

    # ── write_predictions ───────────────────────────────────────────

    async def write_predictions(
        self,
        results: AsyncIterator[PredictionResult],
        *,
        job_id: str,
        model_id: str,
        model_version: str | None = None,
        batch_size: int = 500,
    ) -> int:
        """Persist predictions as per-job parquet shards.

        Writes ``predictions/{job_id}/{shard_index}.parquet`` followed by a
        lightweight ``job_result.json`` manifest.
        """

        prefix = self._prediction_job_prefix(job_id)
        shard_index = 0
        total = 0
        total_successful = 0
        batch: list[PredictionResult] = []
        shard_entries: list[tuple[str, int]] = []

        async for r in results:
            batch.append(r)
            if len(batch) >= batch_size:
                shard_uri = await self._write_prediction_shard(
                    batch,
                    prefix,
                    shard_index,
                    job_id=job_id,
                    model_id=model_id,
                    model_version=model_version,
                )
                shard_entries.append((shard_uri, len(batch)))
                total += len(batch)
                total_successful += sum(1 for item in batch if not item.error)
                shard_index += 1
                batch.clear()

        if batch:
            shard_uri = await self._write_prediction_shard(
                batch,
                prefix,
                shard_index,
                job_id=job_id,
                model_id=model_id,
                model_version=model_version,
            )
            shard_entries.append((shard_uri, len(batch)))
            total += len(batch)
            total_successful += sum(1 for item in batch if not item.error)

        manifest_payload = {
            "job_id": job_id,
            "model_id": model_id,
            "model_version": model_version,
            "total_processed": total,
            "total_successful": total_successful,
            "total_predictions": total,
            "shard_count": len(shard_entries),
            "shards": [
                {
                    "shard_uri": shard_uri,
                    "shard_index": index,
                    "row_count": row_count,
                    "model_id": model_id,
                    "model_version": model_version,
                }
                for index, (shard_uri, row_count) in enumerate(shard_entries)
            ],
        }
        await self._storage.put_bytes(
            object_name=f"{prefix}job_result.json",
            data=_json.dumps(manifest_payload).encode("utf-8"),
            content_type="application/json",
        )
        if shard_entries:
            await self._merge_accumulated_predictions(
                [shard_uri for shard_uri, _ in shard_entries],
                job_id=job_id,
                job_row_count=total,
            )
        return total

    async def _write_prediction_shard(
        self,
        batch: list[PredictionResult],
        prefix: str,
        shard_index: int,
        *,
        job_id: str,
        model_id: str,
        model_version: str | None,
    ) -> str:
        import pyarrow.parquet as pq

        rows: list[dict[str, Any]] = []
        for r in batch:
            rows.append(
                {
                    "sample_id": r.sample_id,
                    "predicted_label": r.predicted_label,
                    "confidence": r.confidence,
                    "all_scores": _json.dumps(r.all_scores) if r.all_scores else None,
                    "model_id": model_id,
                    "target": r.target,
                    "model_version": model_version,
                    "job_id": job_id,
                    "error": r.error,
                }
            )

        table = pa.Table.from_pylist(rows, schema=SPARSE_PREDICTION_SCHEMA)
        buf = _io.BytesIO()
        pq.write_table(table, buf, compression="snappy")

        return await self._storage.put_bytes(
            object_name=f"{prefix}{shard_index:04d}.parquet",
            data=buf.getvalue(),
            content_type="application/octet-stream",
        )

    async def _merge_accumulated_predictions(
        self,
        new_prediction_uris: list[str],
        *,
        job_id: str,
        job_row_count: int,
    ) -> None:
        import duckdb

        if not new_prediction_uris:
            return
        manifest = await self._get_manifest()
        full_coverage = job_row_count >= manifest.total_rows
        source_uris = list(new_prediction_uris)
        if not full_coverage:
            source_uris = [*await self._accumulated_prediction_uris(), *source_uris]

        with tempfile.TemporaryDirectory(
            prefix="sparse-prediction-compact-"
        ) as temporary_directory:
            source_paths: list[str] = []
            for index, uri in enumerate(source_uris):
                path = f"{temporary_directory}/source-{index:06d}.parquet"
                await self._storage.get_file(uri, path)
                source_paths.append(path)
            output_path = f"{temporary_directory}/current.parquet"
            temp_path = f"{temporary_directory}/duckdb-temp"
            connection = duckdb.connect(":memory:")
            try:
                connection.execute(
                    "SET memory_limit = ?",
                    [self._prediction_compaction_memory_limit],
                )
                connection.execute("SET temp_directory = ?", [temp_path])
                connection.execute(
                    "SET max_temp_directory_size = ?",
                    [self._prediction_compaction_temp_limit],
                )
                connection.execute("SET threads = 1")
                connection.execute("SET preserve_insertion_order = false")
                union_sql = " UNION ALL ".join(
                    f"SELECT *, {rank} AS _source_rank "
                    f"FROM read_parquet({_sql_literal(path)}, union_by_name=true)"
                    for rank, path in enumerate(source_paths)
                )
                columns = ", ".join(SPARSE_PREDICTION_COLUMNS)
                connection.execute(
                    f"""
                    COPY (
                        SELECT {columns}
                        FROM (
                            SELECT *, row_number() OVER (
                                PARTITION BY sample_id
                                ORDER BY _source_rank DESC
                            ) AS _latest_rank
                            FROM ({union_sql})
                        )
                        WHERE _latest_rank = 1
                    ) TO {_sql_literal(output_path)} (
                        FORMAT PARQUET,
                        COMPRESSION ZSTD,
                        ROW_GROUP_SIZE {self._prediction_compaction_row_group_rows}
                    )
                    """
                )
            finally:
                connection.close()

            snapshot_name = (
                f"{self._final_prediction_prefix()}snapshot-"
                f"{job_id}-{_uuid.uuid4().hex}.parquet"
            )
            snapshot_uri = await self._storage.put_file(
                object_name=snapshot_name,
                path=output_path,
                content_type="application/octet-stream",
            )
        pointer = {
            "snapshot_uri": snapshot_uri,
            "job_id": job_id,
            "job_row_count": job_row_count,
            "full_coverage": full_coverage,
        }
        await self._storage.put_bytes(
            object_name=f"{self._final_prediction_prefix()}{_CURRENT_PREDICTION_POINTER}",
            data=_json.dumps(pointer, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )

    async def list_predictions(
        self,
        *,
        job_id: str | None = None,
        offset: int = 0,
        limit: int | None = None,
        latest_per_sample: bool = False,
    ) -> list[PredictionResult]:
        if latest_per_sample and job_id is not None:
            raise ValueError("latest_per_sample cannot be combined with job_id")

        lf = await self._prediction_lazyframe(job_id)
        if lf is None:
            return []
        page_lf = lf.slice(offset, limit) if limit is not None else lf.slice(offset)
        df = await page_lf.collect_async()

        results: list[PredictionResult] = []
        for row in df.to_dicts():
            all_scores = row.get("all_scores")
            if isinstance(all_scores, str) and all_scores:
                all_scores = _json.loads(all_scores)
            results.append(
                PredictionResult(
                    sample_id=str(row["sample_id"]),
                    predicted_label=str(row.get("predicted_label") or ""),
                    confidence=row.get("confidence"),
                    all_scores=all_scores if isinstance(all_scores, dict) else None,
                    model_id=row.get("model_id"),
                    target=row.get("target"),
                    model_version=row.get("model_version"),
                    job_id=row.get("job_id"),
                    error=row.get("error"),
                )
            )
        return results

    # ── prediction_summary ──────────────────────────────────────────

    async def prediction_summary(self) -> dict:
        """Aggregate prediction parquet shards from object storage."""
        import polars as pl

        pred_lf = await self._prediction_lazyframe()
        if pred_lf is None:
            return {
                "total_predictions": 0,
                "models": [],
                "label_distribution": {},
            }

        total_lf = pred_lf.select(pl.len().alias("total_predictions"))
        models_lf = (
            pred_lf.group_by("model_id")
            .len()
            .rename({"len": "count"})
            .select(
                pl.col("model_id").cast(pl.Utf8),
                pl.col("count"),
            )
        )
        labels_lf = (
            pred_lf.group_by("predicted_label")
            .len()
            .rename({"len": "count"})
            .sort("count", descending=True)
            .limit(50)
            .select(
                pl.col("predicted_label").cast(pl.Utf8),
                pl.col("count"),
            )
        )
        total_df, models_df, labels_df = pl.collect_all(
            [total_lf, models_lf, labels_lf]
        )

        return {
            "total_predictions": int(total_df.item(0, "total_predictions")),
            "models": models_df.to_dicts(),
            "label_distribution": {
                str(row["predicted_label"]): int(row["count"])
                for row in labels_df.to_dicts()
            },
        }

    # ── upsert_sample_feature ───────────────────────────────────────

    async def upsert_sample_feature(
        self,
        sample_id: str,
        embedding: list[float],
        embed_model: str,
    ) -> None:
        """INSERT or UPDATE :class:`SampleFeatureORM` with pgvector
        synchronisation when running on Postgres.
        """
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            row = await session.get(SampleFeatureORM, sample_id)
            if row is None:
                row = SampleFeatureORM(
                    sample_id=sample_id,
                    embedding=embedding,
                    embed_model=embed_model,
                    computed_at=now,
                )
                session.add(row)
            else:
                row.embedding = embedding
                row.embed_model = embed_model
                row.computed_at = now
            await session.commit()

            # Update pgvector column via raw SQL (Postgres only)
            if session.bind is None:
                raise RuntimeError("Database session has no bound engine")
            dialect_name = session.bind.dialect.name
            if dialect_name == "postgresql":
                vec_str = str(embedding)
                await session.execute(
                    text(
                        "UPDATE sample_features SET embedding_vec = "
                        ":vec::vector WHERE sample_id = :sid"
                    ),
                    {"vec": vec_str, "sid": sample_id},
                )
                await session.commit()

    async def get_sample_feature(self, sample_id: str) -> SampleFeature | None:
        manifest = await self._get_manifest()
        if not await self._lookup_locators(manifest, [sample_id]):
            return None
        async with self._session_factory() as session:
            row = await session.get(SampleFeatureORM, sample_id)
            if row is None:
                return None
            return SampleFeature(
                sample_id=row.sample_id,
                embedding=row.embedding,
                embed_model=row.embed_model,
                computed_at=row.computed_at,
            )

    # ── similarity_search ───────────────────────────────────────────

    async def similarity_search(
        self,
        embedding: list[float],
        k: int,
        exclude_id: str = "",
    ) -> list[dict]:
        """Brute-force cosine similarity over all features for this
        dataset.

        Loads all sample features whose ``sample_id`` appears in the
        sparse manifest, computes cosine similarity against *embedding*
        in Python, and returns the top-*k* results sorted by descending
        score.
        """
        manifest = await self._get_manifest()
        manifest_ids = set(await self._all_sample_ids(manifest))

        import math

        async with self._session_factory() as session:
            sql = text("""
                SELECT sf.sample_id, sf.embedding
                FROM sample_features sf
                WHERE sf.sample_id != :exclude
            """)
            rows = (await session.execute(sql, {"exclude": exclude_id})).fetchall()

            if not rows:
                return []

            def _cosine(a: list[float], b: list[float]) -> float:
                dot = sum(x * y for x, y in zip(a, b))
                na = math.sqrt(sum(x * x for x in a))
                nb = math.sqrt(sum(x * x for x in b))
                if na == 0 or nb == 0:
                    return 0.0
                return dot / (na * nb)

            scored: list[dict] = []
            for row in rows:
                candidate_id = str(row[0])
                if candidate_id not in manifest_ids:
                    continue
                candidate_embedding: Any = row[1]
                if not candidate_embedding:
                    continue
                if isinstance(candidate_embedding, str):
                    candidate_embedding = _json.loads(candidate_embedding)
                score = _cosine(embedding, candidate_embedding)
                scored.append({"sample_id": candidate_id, "score": score})

            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:k]

    # ── materialize ─────────────────────────────────────────────────

    async def materialize(self) -> MaterializeResult:
        """Export all samples from sparse shards into a single flat
        parquet payload in object storage.

        Reads every shard referenced by the manifest, extracts embedded
        image bytes from the ``images`` column where available, and
        writes the result to
        ``materialized/{dataset_id}/{uuid}/materialized.parquet``.
        """
        import uuid as _uuid

        import pyarrow as pa
        import pyarrow.parquet as pq

        manifest = await self._get_manifest()

        rows_data: list[dict[str, object]] = []
        for shard in sorted(manifest.shards, key=lambda s: s.shard_index):
            if shard.row_count == 0:
                continue

            parquet_rows = await self._reader.read_row_batch(
                shard.uri,
                0,
                shard.row_count,
                self._storage,
                columns=["sample_id", "images"],
            )
            for row in parquet_rows:
                sample_id = str(row.get("sample_id", ""))
                row_dict: dict[str, object] = {"sample_id": sample_id}

                images_raw = row.get("images")
                images_list: list[dict[str, object]] = (
                    images_raw if isinstance(images_raw, list) else []
                )
                for img in images_list:
                    if not isinstance(img, dict):
                        continue
                    img_bytes = img.get("bytes")
                    if isinstance(img_bytes, bytes) and img_bytes:
                        row_dict["image_bytes"] = img_bytes
                        break

                rows_data.append(row_dict)

        buf = _io.BytesIO()
        table = pa.Table.from_pylist(rows_data, schema=SPARSE_MATERIALIZED_SCHEMA)
        pq.write_table(table, buf, compression="snappy")

        parquet_bytes = buf.getvalue()
        row_count = len(rows_data)

        prefix = f"materialized/{self._dataset_id}/{_uuid.uuid4().hex[:8]}/"
        parquet_key = f"{prefix}materialized.parquet"
        manifest_uri = await self._storage.put_bytes(
            object_name=parquet_key,
            data=parquet_bytes,
            content_type="application/octet-stream",
        )

        return MaterializeResult(
            manifest_uri=manifest_uri,
            runtime_bucket="finetune-runtime-inputs",
            prefix=prefix,
            row_count=row_count,
        )

    # ── recent_annotations ──────────────────────────────────────────

    async def recent_annotations(self, limit: int = 20) -> dict:
        """Return the most recent annotations for this dataset.

        Projection, ordering, and limiting stay in the lazy Parquet query so
        the caller does not build the entire annotation history in Python.
        """
        if limit <= 0:
            return {"entries": []}
        history = await self._annotation_history_lazyframe()
        if history is None:
            return {"entries": []}
        frame = await (
            history.select(
                "annotation_id",
                "sample_id",
                "label",
                "created_by",
                "created_at",
            )
            .sort("created_at", descending=True)
            .limit(limit)
            .collect_async(engine="streaming")
        )

        return {
            "entries": [
                {
                    "id": str(row["annotation_id"]),
                    "sample_id": str(row["sample_id"]),
                    "label": str(row["label"] or ""),
                    "created_by": str(row["created_by"] or ""),
                    "created_at": str(row["created_at"] or ""),
                }
                for row in frame.to_dicts()
            ]
        }

    # ── delete_samples ──────────────────────────────────────────────

    async def delete_samples(self, sample_ids: list[str]) -> int:
        """Soft-delete samples — remove from manifest sample_index and
        rewrite affected parquet shards without the deleted rows."""
        if not sample_ids:
            return 0

        manifest = await self._get_manifest()

        if manifest.manifest_version == "v3":
            raise NotImplementedError(
                "deleting samples from manifest-v3 sparse datasets requires an "
                "atomic shard and index rewrite"
            )

        to_delete: list[tuple[str, SampleLocator]] = []
        for sid in sample_ids:
            locator = manifest.sample_index.get(sid)
            if locator is not None:
                to_delete.append((sid, locator))

        if not to_delete:
            return 0

        by_shard: dict[int, list[tuple[str, int]]] = {}
        for sid, locator in to_delete:
            by_shard.setdefault(locator.shard_index, []).append(
                (sid, locator.row_index)
            )

        import pyarrow.parquet as pq

        for shard_index, items in by_shard.items():
            if shard_index < 0 or shard_index >= len(manifest.shards):
                continue

            shard = manifest.shards[shard_index]
            shard_bytes = await self._storage.get_bytes(shard.uri)
            table = pq.read_table(_io.BytesIO(shard_bytes))

            remove_rows = {row_idx for _, row_idx in items}
            keep_indices = [i for i in range(table.num_rows) if i not in remove_rows]

            if len(keep_indices) == table.num_rows:
                continue

            keep_table = table.take(keep_indices)

            if "id" in keep_table.column_names:
                sample_col = "id"
            elif "sample_id" in keep_table.column_names:
                sample_col = "sample_id"
            else:
                sample_col = None

            if sample_col is not None:
                remaining_ids = [
                    str(v) for v in keep_table.column(sample_col).to_pylist()
                ]
                for new_idx, rid in enumerate(remaining_ids):
                    loc = manifest.sample_index.get(rid)
                    if loc is not None:
                        loc.row_index = new_idx

            buf = _io.BytesIO()
            pq.write_table(keep_table, buf, compression="snappy")
            new_data = buf.getvalue()

            new_entry = await self._payload_store.put_shard(
                dataset_id=self._dataset_id,
                org_id=self._org_id,
                shard_index=shard_index,
                data=new_data,
                row_count=len(keep_indices),
            )
            manifest.shards[shard_index] = new_entry

        for sid, _ in to_delete:
            manifest.sample_index.pop(sid, None)

        manifest.total_rows = len(manifest.sample_index)
        await self._payload_store.put_manifest(manifest, org_id=self._org_id)
        self._manifest = manifest

        return len(to_delete)

    # ── delete ──────────────────────────────────────────────────────

    async def delete(self) -> None:
        """Completely remove this dataset's object payload and metadata record."""
        await self._payload_store.delete_dataset_payload(self._dataset_id, self._org_id)

        ann_prefix = (
            self._annotations.get_annotations_prefix(self._dataset_id, self._org_id)
            + "/"
        )
        for uri in await self._storage.list_prefix(ann_prefix):
            await self._storage.delete(uri)

        pred_prefix = f"datasets/{self._org_id}/{self._dataset_id}/predictions/"
        for uri in await self._storage.list_prefix(pred_prefix):
            await self._storage.delete(uri)

        self._manifest = None
        self._payload_store.invalidate_manifest(self._dataset_id, self._org_id)

        deleted = await self._repo.delete_dataset(self._dataset_id, self._org_id)
        if not deleted:
            raise RuntimeError(
                f"Dataset metadata disappeared during deletion: {self._dataset_id}"
            )


def _fingerprint_uris(uris: list[str]) -> str:
    digest = hashlib.sha256()
    for uri in uris:
        digest.update(uri.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _annotation_from_sparse_record(record: SparseAnnotationRecord) -> Annotation:
    return Annotation(
        id=record.annotation_id,
        sample_id=record.sample_id,
        label=record.label,
        annotation_value=(
            _json.loads(record.annotation_value) if record.annotation_value else None
        ),
        created_by=record.created_by,
        created_at=(
            datetime.fromisoformat(record.created_at)
            if record.created_at
            else datetime.now(timezone.utc)
        ),
    )


def _annotation_from_sparse_row(row: dict[str, object]) -> Annotation:
    return _annotation_from_sparse_record(
        SparseAnnotationRecord(
            annotation_id=str(row["annotation_id"]),
            sample_id=str(row["sample_id"]),
            label=str(row["label"] or ""),
            annotation_value=str(row["annotation_value"] or ""),
            created_by=str(row["created_by"] or ""),
            created_at=str(row["created_at"] or ""),
            user_id=str(row["user_id"] or ""),
        )
    )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
