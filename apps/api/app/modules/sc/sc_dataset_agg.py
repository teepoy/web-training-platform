"""SC dataset aggregate — wraps :class:`~app.modules.datasets.domain.storage_agg.DatasetStorageAgg`
and adds SC-specific operations for wafer point listing, bulk annotation, and prediction.

Per CORE_DESIGNS.md §2: SC-specific domain logic lives here, not in the storage
implementations or the shared storage aggregate Protocol.
"""

from __future__ import annotations

import asyncio
import json as _json
import uuid
from typing import Any

import polars as pl

from app.modules.datasets.domain.sample_row import PredictionResult
from app.modules.datasets.domain.storage_agg import DatasetStorageAgg
from app.modules.sc.schemas import ScAnnotationItem
from app.shared.api.schemas import Annotation


class ScDatasetAgg:
    """SC specialization layer that wraps a :class:`DatasetStorageAgg` and
    exposes SC domain operations (wafer point listing, bulk annotation,
    on-dataset prediction).

    All SC-specific coordinate/annotation/prediction logic is isolated
    here so that the storage implementations remain type-agnostic.
    """

    def __init__(self, storage: DatasetStorageAgg) -> None:
        self._storage = storage

    async def list_wafer_points(
        self,
        reticle_size_x: int = 1,
        reticle_size_y: int = 1,
        reticle_offset_x: int = 0,
        reticle_offset_y: int = 0,
    ) -> list[dict]:
        """List all wafer points with computed die / reticle coordinates.

        Returns one dict per sample with keys:
        ``defect_id``, ``wafer_x``, ``wafer_y``, ``die_x``, ``die_y``,
        ``reticle_x``, ``reticle_y``, ``class_number``, ``rough_bin``.

        When the storage backend exposes a polars LazyFrame with SC
        coordinate columns (``wafer_x``, ``wafer_y``, and optionally
        ``origin_x``, ``origin_y``, ``die_size_x``, ``die_size_y``),
        die and reticle coordinates are computed via polars expressions.

        For storage backends that do **not** carry SC columns in their
        lazy projection (e.g. ``db_full`` where coordinate metadata lives
        inside ``metadata_json``), the method falls back to extracting
        rows in Python.
        """
        lf: pl.LazyFrame = await self._storage.list_samples(  # type: ignore[assignment]
            return_lazyframe=True
        )

        cols: set[str] = set(lf.columns)

        if "wafer_x" in cols and "wafer_y" in cols:
            return await self._compute_wafer_points_polars(
                lf,
                reticle_size_x=reticle_size_x,
                reticle_size_y=reticle_size_y,
                reticle_offset_x=reticle_offset_x,
                reticle_offset_y=reticle_offset_y,
                cols=cols,
            )

        return await self._compute_wafer_points_python(lf)

    async def _compute_wafer_points_polars(
        self,
        lf: pl.LazyFrame,
        *,
        reticle_size_x: int,
        reticle_size_y: int,
        reticle_offset_x: int,
        reticle_offset_y: int,
        cols: set[str],
    ) -> list[dict]:
        """Compute die / reticle coordinates via polars expressions.

        When ``origin_x``, ``origin_y``, ``die_size_x``, ``die_size_y``
        are present the full die-geometry computation is used.  Otherwise
        wafer coordinates are used directly as die coordinates and reticle
        coordinates are derived from wafer position.
        """
        has_geo = all(
            c in cols for c in ("origin_x", "origin_y", "die_size_x", "die_size_y")
        )
        has_die = "die_x" in cols and "die_y" in cols

        if has_geo:
            lf = lf.with_columns(
                ((pl.col("wafer_x") - pl.col("origin_x")) % pl.col("die_size_x")).alias(
                    "die_x"
                ),
                ((pl.col("wafer_y") - pl.col("origin_y")) % pl.col("die_size_y")).alias(
                    "die_y"
                ),
            )
            lf = lf.with_columns(
                (
                    pl.col("die_x")
                    + (
                        (pl.col("wafer_x") - pl.col("origin_x")) // pl.col("die_size_x")
                        + reticle_offset_x
                    )
                    % reticle_size_x
                    * pl.col("die_size_x")
                ).alias("reticle_x"),
                (
                    pl.col("die_y")
                    + (
                        (pl.col("wafer_y") - pl.col("origin_y")) // pl.col("die_size_y")
                        + reticle_offset_y
                    )
                    % reticle_size_y
                    * pl.col("die_size_y")
                ).alias("reticle_y"),
            )
        else:
            if not has_die:
                lf = lf.with_columns(
                    pl.col("wafer_x").alias("die_x"),
                    pl.col("wafer_y").alias("die_y"),
                )
            if reticle_size_x > 1 or reticle_size_y > 1:
                lf = lf.with_columns(
                    ((pl.col("wafer_x") + reticle_offset_x) % reticle_size_x).alias(
                        "reticle_x"
                    ),
                    ((pl.col("wafer_y") + reticle_offset_y) % reticle_size_y).alias(
                        "reticle_y"
                    ),
                )
            else:
                lf = lf.with_columns(
                    pl.col("wafer_x").alias("reticle_x"),
                    pl.col("wafer_y").alias("reticle_y"),
                )

        if "class_number" not in cols:
            lf = lf.with_columns(pl.lit(None).alias("class_number"))
        if "rough_bin" not in cols:
            lf = lf.with_columns(pl.lit(0).alias("rough_bin"))
        if "defect_id" not in cols:
            sid_col = "sample_id" if "sample_id" in cols else "id"
            lf = lf.with_columns(pl.col(sid_col).alias("defect_id"))

        select_cols = [
            "defect_id",
            "wafer_x",
            "wafer_y",
            "die_x",
            "die_y",
            "reticle_x",
            "reticle_y",
            "class_number",
            "rough_bin",
        ]
        return (await lf.select(select_cols).collect_async()).to_dicts()

    async def _compute_wafer_points_python(self, lf: pl.LazyFrame) -> list[dict]:
        """Fallback path for backends that carry SC coordinates inside
        ``metadata_json`` (e.g. ``db_full`` storage).

        Collects the lazyframe, extracts coordinate fields from each
        row's metadata dict, and computes die/reticle as wafer position.
        """
        df = await lf.collect_async()
        rows: list[dict] = []

        for row in df.iter_rows(named=True):
            meta: dict[str, Any] = row.get("metadata_json") or {}
            if isinstance(meta, str):
                try:
                    meta = _json.loads(meta)
                except (_json.JSONDecodeError, TypeError):
                    meta = {}

            wx: int = int(meta.get("wafer_x", 0))
            wy: int = int(meta.get("wafer_y", 0))
            did: str = str(meta.get("defect_id", row.get("id", "")))
            cn: int | None = meta.get("class_number")
            rb: int = int(meta.get("rough_bin", 0))

            if not did:
                did = str(row.get("id", "") or row.get("sample_id", ""))

            rows.append(
                {
                    "defect_id": did,
                    "wafer_x": wx,
                    "wafer_y": wy,
                    "die_x": wx,
                    "die_y": wy,
                    "reticle_x": wx,
                    "reticle_y": wy,
                    "class_number": cn,
                    "rough_bin": rb,
                }
            )

        return rows

    async def bulk_annotate(self, items: list[ScAnnotationItem]) -> int:
        """Convert SC annotation items to storage :class:`Annotation` objects and
        persist them in a single batch.

        SC convention: ``defect_id`` **is** the ``sample_id``.
        """
        if not items:
            return 0

        annotations: list[Annotation] = [
            Annotation(
                sample_id=item.defect_id,
                label=item.label,
                created_by=item.annotator,
            )
            for item in items
        ]

        return await self._storage.create_annotations(annotations)

    async def predict_on_dataset(
        self,
        model_ref: Any,
        *,
        sampling: int | None = None,
        sample_ids: list[str] | None = None,
        job_id: str | None = None,
        model_id: str | None = None,
        model_version: str | None = None,
    ) -> dict:
        """Run prediction over the dataset using *model_ref* and persist results.

        Uses a producer-consumer pattern:

        1. Materialize the dataset as a HuggingFace ``Dataset`` via
           ``as_hf_dataset("patch_image_v1", ...)``.
        2. A *prediction task* iterates the HF dataset, calls
           ``model_ref(sample)`` for each sample, and places
           :class:`~app.modules.datasets.domain.sample_row.PredictionResult`
           entries into an async queue.
        3. An *upload task* drains the queue in batches and persists
           predictions through ``write_predictions``.
        4. Both tasks run concurrently; the method returns a summary
           once both are complete.

        Parameters
        ----------
        model_ref:
            Callable ``(sample: dict) -> dict`` that returns a
            prediction dict with keys ``predicted_label``,
            ``confidence`` (optional), ``all_scores`` (optional).
        sampling:
            Maximum number of samples to predict (passed through to
            ``as_hf_dataset``).
        sample_ids:
            Specific sample IDs to predict (passed through to
            ``as_hf_dataset``).
        job_id:
            Job identifier for persisted predictions.  Auto-generated
            when omitted.
        model_id:
            Model identifier for provenance.  Defaults to ``"unknown"``.
        model_version:
            Model version for provenance.

        Returns
        -------
        dict
            Summary with keys ``total``, ``job_id``, ``model_id``,
            ``error_count``.
        """
        _job_id: str = job_id or str(uuid.uuid4())
        _model_id: str = model_id or getattr(model_ref, "model_id", "unknown")
        _model_version: str | None = model_version

        ds = await self._storage.as_hf_dataset(
            "patch_image_v1",
            sampling=sampling,
            sample_ids=sample_ids,
        )

        queue: asyncio.Queue[PredictionResult | object] = asyncio.Queue(maxsize=256)
        _SENTINEL: object = object()

        async def _prediction_task() -> int:
            error_count = 0
            ds_len: int = len(ds)  # type: ignore[arg-type]
            for i in range(ds_len):
                sample: dict = ds[i]  # type: ignore[index]
                sample_id: str = str(
                    sample.get("sample_id", sample.get("defect_id", f"idx_{i}"))
                )
                try:
                    result: dict = model_ref(sample)
                    predicted_label: str = str(
                        result.get("predicted_label", result.get("label", ""))
                    )
                    confidence: float | None = result.get("confidence")
                    all_scores: dict[str, float] | None = result.get("all_scores")
                    error: str | None = result.get("error")
                except Exception as exc:
                    predicted_label = ""
                    confidence = None
                    all_scores = None
                    error = str(exc)
                    error_count += 1

                await queue.put(
                    PredictionResult(
                        sample_id=sample_id,
                        predicted_label=predicted_label,
                        confidence=confidence,
                        all_scores=all_scores,
                        model_id=_model_id,
                        job_id=_job_id,
                        model_version=_model_version,
                        error=error,
                    )
                )

            await queue.put(_SENTINEL)
            return error_count

        async def _upload_task() -> int:
            return await self._storage.write_predictions(
                _queue_reader(queue, _SENTINEL),
                job_id=_job_id,
                model_id=_model_id,
                model_version=_model_version,
            )

        producer_coro = asyncio.create_task(_prediction_task())
        consumer_coro = asyncio.create_task(_upload_task())

        total_written, error_count = await asyncio.gather(consumer_coro, producer_coro)

        return {
            "total": total_written,
            "job_id": _job_id,
            "model_id": _model_id,
            "error_count": error_count,
        }


async def _queue_reader(
    queue: asyncio.Queue[PredictionResult | object],
    sentinel: object,
) -> Any:
    while True:
        item = await queue.get()
        if item is sentinel:
            break
        yield item
