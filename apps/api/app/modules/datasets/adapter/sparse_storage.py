from __future__ import annotations

import io as _io
import json as _json
import random
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from platform_runtime.sparse import (
    DatasetPayloadStore,
    SparseAnnotationRecord,
    SparseAnnotationStore,
    SparseManifestReader,
    build_annotation_record,
)
from platform_runtime.sparse.models import (
    ColumnSchema,
    DatasetManifest,
    SampleLocator,
    ShardEntry,
)

from app.modules.datasets.app.services.sparse_import_operator import (
    SparseImportOperator,
)
from app.modules.datasets.domain.sample_row import (
    BulkSampleRow,
    PredictionResult,
    SampleRow,
    SampleRowImageRef,
)
from app.modules.datasets.domain.storage_agg import (
    Capabilities,
    MaterializeResult,
)
from app.shared.api.schemas import Annotation, DatasetStorageMode
from app.shared.db.registry import SampleFeatureORM
from app.shared.domain.protocols import ArtifactStorage, LabelStudioClient

_SCAN_PARQUET_SCHEMES = ("s3://", "file://")


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
    :class:`~platform_runtime.sparse.annotations.SparseAnnotationStore`.
    Implements the ``DatasetStorageAgg`` Protocol structurally (no
    inheritance).
    """

    _MODE: DatasetStorageMode = DatasetStorageMode.FILE_SHARD_SPARSE

    def __init__(
        self,
        dataset_id: str,
        org_id: str | None,
        storage: ArtifactStorage,
        payload_store: DatasetPayloadStore,
        ls_client: LabelStudioClient | None = None,
        session_factory: async_sessionmaker | None = None,
        repo: Any = None,
        dataset_type: str = "",
    ) -> None:
        self._dataset_id: str = dataset_id
        self._org_id: str = org_id or ""
        self._storage: ArtifactStorage = storage
        self._payload_store: DatasetPayloadStore = payload_store
        self._ls_client: LabelStudioClient | None = ls_client
        self._session_factory: async_sessionmaker | None = session_factory
        self._repo: Any = repo
        self._reader: SparseManifestReader = SparseManifestReader()
        self._annotations: SparseAnnotationStore = SparseAnnotationStore(storage)
        self._dataset_type: str = dataset_type

        # Lazy-loaded manifest cache.
        self._manifest: DatasetManifest | None = None

    # ── properties ──────────────────────────────────────────────────

    @property
    def dataset_id(self) -> str:
        return self._dataset_id

    @property
    def storage_mode(self) -> DatasetStorageMode:
        return self._MODE

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            can_write_samples=True,
            can_random=True,
            can_similarity=True,
            can_materialize=True,
            can_lazyframe=True,
        )

    # ── metadata ────────────────────────────────────────────────────

    async def get_dataset_metadata(self) -> Any:
        """Return the Dataset metadata record via the injected repository.

        Returns ``None`` when no repository was wired (e.g. in tests that
        construct the storage directly without the composition root).
        """
        if self._repo is None:
            return None
        return await self._repo.get_dataset(self._dataset_id, self._org_id)

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

    def _row_to_sample_row(self, row: dict[str, object]) -> SampleRow:
        """Convert a raw parquet row dict to a :class:`SampleRow`."""
        sample_id = self._extract_sample_id(row)

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

    async def _read_parquet_uris_fallback(self, uris: list[str]) -> Any | None:
        """Compatibility path for in-memory test storage that has no scan URI."""
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

    async def _parquet_uris_to_lazyframe(
        self, uris: list[str], *, allow_fallback: bool = True
    ) -> Any | None:
        lf = self._scan_parquet_uris(uris)
        if lf is not None or not allow_fallback:
            return lf
        return await self._read_parquet_uris_fallback(uris)

    async def _prediction_lazyframe(
        self, prediction_job_id: str | None = None
    ) -> Any | None:
        prefix = f"datasets/{self._org_id}/{self._dataset_id}/predictions/"
        if prediction_job_id is not None:
            prefix = f"{prefix}{prediction_job_id}/"
        try:
            uris = await self._storage.list_prefix(prefix)
        except Exception:
            return None
        return await self._parquet_uris_to_lazyframe(uris)

    async def _latest_annotation_lazyframe(self) -> Any | None:
        import polars as pl

        prefix = (
            self._annotations.get_annotations_prefix(self._dataset_id, self._org_id)
            + "/"
        )
        try:
            uris = await self._storage.list_prefix(prefix)
        except Exception:
            return None
        ann_lf = await self._parquet_uris_to_lazyframe(uris)
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
                pl.col("label").last().cast(pl.Utf8).alias("label"),
                pl.col("annotation_value")
                .last()
                .cast(pl.Utf8)
                .alias("annotation_value"),
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
                pl.col("predicted_label").last().cast(pl.Utf8).alias("predicted_label")
            )
        )

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
                access_url = (
                    f"/api/v1/sc/datasets/{self._dataset_id}/samples/"
                    f"{sample_id}/images/{image_id}"
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

        # ── resolve candidate sample_ids ─────────────────────────
        if sample_ids is not None:
            if len(sample_ids) == 0:
                return [], 0
            wanted = set(sample_ids)
            all_sids = [sid for sid in manifest.sample_index if sid in wanted]
        else:
            all_sids = list(manifest.sample_index.keys())

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
            all_sids = self._sorted_shard_ids(manifest, all_sids)

        # ── predictions ──────────────────────────────────────────
        predictions_by_sample: dict[str, Any] = {}
        if with_predictions or prediction_job_id is not None:
            predictions_by_sample = await self._load_predictions(
                prediction_job_id=prediction_job_id, manifest=manifest
            )

        total = len(all_sids)

        # ── paginate ─────────────────────────────────────────────
        page_ids = all_sids[offset : offset + limit]

        # ── build SampleRow objects ──────────────────────────────
        result: list[SampleRow] = []
        for sid in page_ids:
            locator = manifest.sample_index.get(sid)
            if locator is None:
                continue

            raw_row = await self._read_sample_from_locator(locator, manifest)
            if raw_row is None:
                continue

            sr = self._row_to_sample_row(raw_row)

            if with_labels:
                entry = latest_by_sample.get(sid)
                if entry is not None:
                    sr.latest_label = entry.label

            if with_predictions:
                pred = predictions_by_sample.get(sid)
                if pred is not None:
                    sr.latest_prediction = {
                        "predicted_label": pred.get("predicted_label"),
                        "confidence": pred.get("confidence"),
                        "all_scores": pred.get("all_scores"),
                        "model_id": pred.get("model_id"),
                        "target": pred.get("target"),
                        "model_version": pred.get("model_version"),
                        "job_id": pred.get("job_id"),
                        "error": pred.get("error"),
                    }

            result.append(sr)

        return result, total

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
    ) -> dict[str, dict[str, Any]]:
        """Load prediction results, optionally filtered by job_id.

        Predictions are stored as per-job parquet files under
        ``datasets/{org_id}/{dataset_id}/predictions/``.
        """
        import pyarrow.parquet as pq

        prefix = f"datasets/{self._org_id}/{self._dataset_id}/predictions/"
        if prediction_job_id is not None:
            prefix = f"{prefix}{prediction_job_id}/"

        try:
            uris = await self._storage.list_prefix(prefix)
        except Exception:
            return {}

        results: dict[str, dict[str, Any]] = {}
        for uri in uris:
            try:
                raw = await self._storage.get_bytes(uri)
                table = pq.read_table(_io.BytesIO(raw))
                rows = table.to_pylist()
                for row in rows:
                    sid = str(row.get("sample_id", ""))
                    if sid:
                        all_scores = row.get("all_scores")
                        if isinstance(all_scores, str):
                            try:
                                all_scores = _json.loads(all_scores)
                            except (TypeError, ValueError):
                                all_scores = None
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
            except Exception:
                continue

        return results

    # ── get_sample ──────────────────────────────────────────────────

    async def get_sample(self, sample_id: str) -> SampleRow | None:
        """Look up a single sample by id via the manifest sample_index."""
        manifest = await self._get_manifest()
        locator = manifest.sample_index.get(sample_id)
        if locator is None:
            return None

        raw_row = await self._read_sample_from_locator(locator, manifest)
        if raw_row is None:
            return None

        return self._row_to_sample_row(raw_row)

    # ── get_samples_batch ───────────────────────────────────────────

    async def get_samples_batch(self, sample_ids: list[str]) -> list[SampleRow | None]:
        """Batch-lookup samples, grouping reads by shard for efficiency."""
        if not sample_ids:
            return []

        manifest = await self._get_manifest()

        # Group sample_ids by shard_index
        by_shard: dict[int, list[tuple[str, int]]] = {}
        id_to_locator: dict[str, SampleLocator] = {}
        sid_order: list[str] = []

        for sid in sample_ids:
            locator = manifest.sample_index.get(sid)
            if locator is not None:
                id_to_locator[sid] = locator
                by_shard.setdefault(locator.shard_index, []).append(
                    (sid, locator.row_index)
                )
            sid_order.append(sid)

        # Read each shard once, extract all requested rows
        shard_rows: dict[str, dict[str, object]] = {}
        for shard_index, items in by_shard.items():
            if shard_index < 0 or shard_index >= len(manifest.shards):
                continue
            shard = manifest.shards[shard_index]

            # Sort by row_index and read contiguous ranges where possible.
            items_sorted = sorted(items, key=lambda x: x[1])
            for sid, row_index in items_sorted:
                if row_index < 0 or row_index >= shard.row_count:
                    continue
                # Read single row (could batch contiguous reads later)
                rows = await self._reader.read_row_batch(
                    shard.uri, row_index, 1, self._storage
                )
                if rows:
                    shard_rows[sid] = rows[0]

        # Build result in input order
        result: list[SampleRow | None] = []
        for sid in sid_order:
            raw = shard_rows.get(sid)
            if raw is not None:
                result.append(self._row_to_sample_row(raw))
            else:
                result.append(None)

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
        image_struct = pa.struct(
            [
                pa.field("image_id", pa.string()),
                pa.field("image_type", pa.string()),
                pa.field("role", pa.string()),
                pa.field("content_type", pa.string()),
                pa.field("filename", pa.string()),
                pa.field("bytes", pa.binary()),
                pa.field("source_uri", pa.string()),
            ]
        )

        fields = [
            pa.field("id", pa.string()),
            pa.field("sample_id", pa.string()),
            pa.field("images", pa.list_(image_struct)),
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
                        "source_uri": img.source_uri or "",
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
        a :class:`~platform_runtime.sparse.SparseAnnotationRecord` and
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
        existing = await self._annotations.load_all(
            dataset_id=self._dataset_id, org_id=self._org_id
        )

        # Build annotation_id → existing record lookup
        id_to_rec: dict[str, SparseAnnotationRecord] = {}
        for rec in existing:
            id_to_rec[rec.annotation_id] = rec

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
        existing = await self._annotations.load_all(
            dataset_id=self._dataset_id, org_id=self._org_id
        )

        # Filter out deleted annotation_ids
        remaining = [r for r in existing if r.annotation_id not in doomed]
        deleted_count = len(existing) - len(remaining)
        if deleted_count == 0:
            return 0

        # Compute latest-per-sample from remaining records
        latest: dict[str, SparseAnnotationRecord] = {}
        for r in remaining:
            cur = latest.get(r.sample_id)
            if cur is None or r.created_at >= cur.created_at:
                latest[r.sample_id] = r

        # Rewrite with fresh timestamps so they supersede old parquet files
        if latest:
            fresh: list[SparseAnnotationRecord] = []
            for r in latest.values():
                fresh.append(
                    SparseAnnotationRecord(
                        annotation_id=r.annotation_id,
                        sample_id=r.sample_id,
                        label=r.label,
                        annotation_value=r.annotation_value,
                        created_by=r.created_by,
                        created_at=datetime.now(timezone.utc).isoformat(),
                        user_id=r.user_id,
                    )
                )
            await self._annotations.append(
                dataset_id=self._dataset_id,
                org_id=self._org_id,
                items=fresh,
            )

        return deleted_count

    # ── get_annotation_stats ────────────────────────────────────────

    async def get_annotation_stats(self) -> dict[str, int]:
        """Return per-label annotation counts.

        Delegates to :meth:`SparseAnnotationStore.stats`, which computes
        counts via ``latest_by_sample()`` without loading every record
        into a flat list.
        """
        return await self._annotations.stats(
            dataset_id=self._dataset_id, org_id=self._org_id
        )

    # ── list_annotations ───────────────────────────────────────────

    async def list_annotations(
        self,
        *,
        sample_id: str | None = None,
        dataset_id: str | None = None,
        limit: int | None = None,
    ) -> list[Annotation]:
        items = await self._annotations.load_all(
            dataset_id=self._dataset_id, org_id=self._org_id
        )
        if sample_id:
            items = [i for i in items if i.sample_id == sample_id]
        if limit is not None:
            items = items[:limit]
        return [
            Annotation(
                id=item.annotation_id,
                sample_id=item.sample_id,
                label=item.label,
                annotation_value=(
                    _json.loads(item.annotation_value)
                    if item.annotation_value
                    else None
                ),
                created_by=item.created_by,
                created_at=datetime.fromisoformat(item.created_at)
                if item.created_at
                else datetime.now(timezone.utc),
            )
            for item in items
        ]

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

        prefix = f"datasets/{self._org_id}/{self._dataset_id}/predictions/{job_id}/"
        shard_index = 0
        total = 0
        batch: list[PredictionResult] = []

        async for r in results:
            batch.append(r)
            if len(batch) >= batch_size:
                await self._write_prediction_shard(
                    batch,
                    prefix,
                    shard_index,
                    job_id=job_id,
                    model_id=model_id,
                    model_version=model_version,
                )
                total += len(batch)
                shard_index += 1
                batch.clear()

        if batch:
            await self._write_prediction_shard(
                batch,
                prefix,
                shard_index,
                job_id=job_id,
                model_id=model_id,
                model_version=model_version,
            )
            total += len(batch)

        manifest_payload = {
            "job_id": job_id,
            "model_id": model_id,
            "model_version": model_version,
            "total_predictions": total,
            "shard_count": shard_index + (1 if batch else 0),
        }
        await self._storage.put_bytes(
            object_name=f"{prefix}job_result.json",
            data=_json.dumps(manifest_payload).encode("utf-8"),
            content_type="application/json",
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
    ) -> None:
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

        table = pa.Table.from_pylist(rows)
        buf = _io.BytesIO()
        pq.write_table(table, buf, compression="snappy")

        await self._storage.put_bytes(
            object_name=f"{prefix}{shard_index:04d}.parquet",
            data=buf.getvalue(),
            content_type="application/octet-stream",
        )

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
        try:
            total_df, models_df, labels_df = pl.collect_all(
                [total_lf, models_lf, labels_lf]
            )
        except Exception:
            return {
                "total_predictions": 0,
                "models": [],
                "label_distribution": {},
            }

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
        if self._session_factory is None:
            raise RuntimeError(
                "SparseDatasetStorage requires a session_factory "
                "for upsert_sample_feature"
            )

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
            try:
                dialect_name = session.bind.dialect.name
            except Exception:
                dialect_name = ""
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
        if self._session_factory is None:
            raise RuntimeError(
                "SparseDatasetStorage requires a session_factory for similarity_search"
            )

        manifest = await self._get_manifest()
        manifest_ids = set(manifest.sample_index.keys())

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
        if rows_data:
            table = pa.Table.from_pylist(rows_data)
            pq.write_table(table, buf, compression="snappy")
        else:
            schema = pa.schema(
                [
                    ("sample_id", pa.string()),
                ]
            )
            pq.write_table(pa.table({}, schema=schema), buf)

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

    # ── as_hf_dataset ───────────────────────────────────────────────

    async def as_hf_dataset(
        self,
        view_id: str,
        *,
        sampling: int | None = None,
        sample_ids: list[str] | None = None,
    ) -> Any:
        """Materialize the dataset, load the resulting parquet as a
        HuggingFace ``Dataset``, apply optional filtering / sampling,
        and clean up temp files afterwards."""
        result = await self.materialize()

        import os
        import tempfile

        manifest_uri = result.manifest_uri

        if not os.path.isfile(manifest_uri):
            parquet_bytes = await self._storage.get_bytes(manifest_uri)
            tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
            tmp.write(parquet_bytes)
            tmp.close()
            parquet_path: str = tmp.name
        else:
            parquet_path = manifest_uri

        try:
            from datasets import load_dataset

            ds = load_dataset("parquet", data_files=parquet_path, split="train")

            if sample_ids is not None:
                sid_set: frozenset[str] = frozenset(sample_ids)
                ds = ds.filter(lambda x: x["sample_id"] in sid_set)

            if sampling is not None and len(ds) > sampling:
                ds = ds.select(range(sampling))

            return ds
        finally:
            if os.path.isfile(parquet_path):
                try:
                    os.unlink(parquet_path)
                except OSError:
                    pass

    # ── recent_annotations ──────────────────────────────────────────

    async def recent_annotations(self, limit: int = 20) -> dict:
        """Return the most recent annotations for this dataset.

        Reads all annotation parquet sidecar files via
        :class:`SparseAnnotationStore`, sorts by ``created_at``
        descending, and limits to *limit* entries.
        """
        records: list[SparseAnnotationRecord] = await self._annotations.load_all(
            dataset_id=self._dataset_id, org_id=self._org_id
        )
        records.sort(key=lambda r: r.created_at, reverse=True)
        recent = records[:limit]

        return {
            "entries": [
                {
                    "id": rec.annotation_id,
                    "sample_id": rec.sample_id,
                    "label": rec.label,
                    "created_by": rec.created_by,
                    "created_at": rec.created_at,
                }
                for rec in recent
            ]
        }

    # ── delete_samples ──────────────────────────────────────────────

    async def delete_samples(self, sample_ids: list[str]) -> int:
        """Soft-delete samples — remove from manifest sample_index and
        rewrite affected parquet shards without the deleted rows."""
        if not sample_ids:
            return 0

        manifest = await self._get_manifest()

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
        """Completely remove this dataset's payload — shards, manifest,
        annotation sidecars, and prediction shards — from object storage."""
        await self._payload_store.delete_dataset_payload(self._dataset_id, self._org_id)

        ann_prefix = (
            self._annotations.get_annotations_prefix(self._dataset_id, self._org_id)
            + "/"
        )
        try:
            for uri in await self._storage.list_prefix(ann_prefix):
                await self._storage.delete(uri)
        except Exception:
            pass

        pred_prefix = f"datasets/{self._org_id}/{self._dataset_id}/predictions/"
        try:
            for uri in await self._storage.list_prefix(pred_prefix):
                await self._storage.delete(uri)
        except Exception:
            pass

        self._manifest = None
        self._payload_store.invalidate_manifest(self._dataset_id, self._org_id)
