"""Sparse prediction result readback and storage helpers.

.. warning::
   **DEPRECATED — DO NOT use :class:`SparsePredictionRunner` for new work.**

   The ``_infer_batch`` method raises ``NotImplementedError`` because
   inference dispatch has been moved to the Prefect flow in
   :mod:`app.modules.prediction.flows.predict_job`.

   Active sparse prediction execution lives in:
   - ``_run_sparse_prediction_job()``
   - ``_run_materialized_sparse_prediction()``
   (both in ``predict_job.py``, dispatched via executable predictor registry)

   The module retains result write/readback helpers
   (``_write_prediction_shard``, ``_write_job_result``, column
   parsers) that are referenced by the canonical flow paths.

Storage contract (unchanged)
-----------------------------
Prediction results for ``file_shard_sparse`` datasets are *not* persisted
as ``PlatformPrediction`` rows in the API database.  Instead they live as
parquet files in object storage, organised under the dataset prefix.

Write layout
~~~~~~~~~~~~
One prediction shard is written for every input dataset shard (1:1 mapping).
The naming convention is::

    datasets/{org_id}/{dataset_id}/predictions/{job_id}/{shard_index:06d}.parquet

Each shard file is a parquet table whose schema mirrors the fields of
:class:`~platform_runtime.sparse.models.SparsePredictionResult`::

    shard_index, row_index, dataset_id,
    predicted_label, confidence, all_scores, error

A top-level job result manifest — serialized from
:class:`~platform_runtime.sparse.models.SparsePredictionJobResult` — is
stored alongside the shards::

    datasets/{org_id}/{dataset_id}/predictions/{job_id}/job_result.json
"""

from __future__ import annotations

import base64
import io
import json
import logging
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from platform_runtime.sparse import (
    DatasetPayloadStore,
    SampleLocator,
    SparseManifestReader,
    SparsePredictionJobResult,
    SparsePredictionResult,
    SparsePredictionShard,
)

try:
    from app.modules.sc.schema import find_images_by_role
except ImportError:  # pragma: no cover
    find_images_by_role = None

if TYPE_CHECKING:
    from omegaconf import DictConfig

    from app.shared.api.schemas import Dataset, Model
    from app.modules.prediction.domain.repository import PredictionRepository
    from app.shared.domain.protocols import (
        ArtifactStorage,
        LlmClient,
    )

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 64
"""Configurable via ``config.sparse_prediction_batch_size`` or env override."""


def _encode_data_uri(image_struct: dict[str, object]) -> str:
    """Encode an SC v2 image struct as a ``data:`` URI.

    Returns a string like ``"data:image/jpeg;base64,/9j/4AAQ..."`` that
    the SC predictor can decode via its existing ``_decode_image_bytes``
    path without requiring S3 storage access.
    """
    raw_bytes = cast(bytes, image_struct["bytes"])
    content_type: str = str(image_struct.get("content_type", "image/png"))
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{content_type};base64,{b64}"


class SparsePredictionRunner:
    """Streaming sparse prediction runner for ``file_shard_sparse`` datasets.

    Key properties:

    * **Bounded batches** — reads at most ``batch_size`` rows at a time from
      Parquet and sends one HTTP inference request per batch.  Never loads
      all 100 k rows into memory or sends them in a single request.
    * **Shard-aligned output** — one prediction Parquet per input shard (1:1
      mapping), plus a ``job_result.json`` manifest for discovery.
    * **Graceful degradation** — per-batch inference errors are captured as
      error rows; the remaining shards continue processing.
    """

    # ------------------------------------------------------------------
    # constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        repository: PredictionRepository,
        artifact_storage: ArtifactStorage,
        config: DictConfig,
        llm_client: LlmClient | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_storage = artifact_storage
        self._config = config
        self._llm_client = llm_client
        self._batch_size = (
            getattr(config, "sparse_prediction_batch_size", None) or _DEFAULT_BATCH_SIZE
        )
        self._store = DatasetPayloadStore(artifact_storage)
        self._reader = SparseManifestReader()

    # ------------------------------------------------------------------
    # public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        model: Model,
        dataset: Dataset,
        *,
        org_id: str = "",
        model_version: str | None = None,
        target: str = "image_classification",
        prompt: str | None = None,
        job_id: str | None = None,
    ) -> SparsePredictionJobResult:
        """Execute sparse prediction across all dataset shards.

        Returns the :class:`SparsePredictionJobResult` that was also
        persisted to object storage as ``job_result.json``.
        """
        job_id = job_id or str(uuid4())

        # ── 1. load manifest ──────────────────────────────────────────
        try:
            manifest = await self._store.get_manifest(dataset.id, org_id)
        except FileNotFoundError:
            logger.warning(
                "No manifest found for dataset %s — producing empty result",
                dataset.id,
            )
            job_result = SparsePredictionJobResult(
                job_id=job_id,
                dataset_id=dataset.id,
                model_id=model.id,
                model_version=model_version,
            )
            await self._write_job_result(job_result, dataset.id, org_id)
            return job_result

        if not manifest.shards:
            logger.info(
                "SparsePredictionRunner: dataset %s has no shards",
                dataset.id,
            )
            job_result = SparsePredictionJobResult(
                job_id=job_id,
                dataset_id=dataset.id,
                model_id=model.id,
                model_version=model_version,
            )
            await self._write_job_result(job_result, dataset.id, org_id)
            return job_result

        # ── 2. prepare inference context ──────────────────────────────
        model_bytes = await self._artifact_storage.get_bytes(model.uri)
        model_metadata = model.metadata if isinstance(model.metadata, dict) else {}
        label_space = list(dataset.task_spec.label_space)

        # ── 3. stream over shards ────────────────────────────────────
        shards_sorted = sorted(manifest.shards, key=lambda s: s.shard_index)

        all_shards: list[SparsePredictionShard] = []
        total_processed = 0
        total_successful = 0

        for shard_entry in shards_sorted:
            logger.info(
                "Processing shard %d/%d (%d rows) batch_size=%d",
                shard_entry.shard_index + 1,
                len(shards_sorted),
                shard_entry.row_count,
                self._batch_size,
            )
            shard_result = await self._process_shard(
                shard_entry=shard_entry,
                model=model,
                model_bytes=model_bytes,
                model_metadata=model_metadata,
                model_version=model_version,
                label_space=label_space,
                target=target,
                prompt=prompt,
                dataset_id=dataset.id,
                org_id=org_id,
                job_id=job_id,
            )
            all_shards.append(shard_result)
            total_processed += shard_entry.row_count
            total_successful += sum(1 for r in shard_result.results if not r.error)

        # ── 4. write job_result.json ─────────────────────────────────
        total_failed = total_processed - total_successful
        job_result = SparsePredictionJobResult(
            job_id=job_id,
            dataset_id=dataset.id,
            model_id=model.id,
            model_version=model_version,
            shards=all_shards,
            total_processed=total_processed,
            total_successful=total_successful,
        )
        await self._write_job_result(job_result, dataset.id, org_id)

        logger.info(
            "SparsePredictionRunner complete: "
            "processed=%d successful=%d failed=%d shards=%d",
            total_processed,
            total_successful,
            total_failed,
            len(all_shards),
        )
        return job_result

    # ------------------------------------------------------------------
    # per-shard processing
    # ------------------------------------------------------------------

    _V2_COLUMNS = ["sample_id", "images"]
    _V1_COLUMNS = ["sample_id", "image_uris", "metadata"]

    async def _process_shard(
        self,
        *,
        shard_entry,
        model,
        model_bytes: bytes,
        model_metadata: dict,
        model_version: str | None,
        label_space: list[str],
        target: str,
        prompt: str | None,
        dataset_id: str,
        org_id: str,
        job_id: str,
    ) -> SparsePredictionShard:
        """Read shard rows in bounded batches, infer, write prediction Parquet."""
        all_results: list[SparsePredictionResult] = []
        effective_columns: list[str] | None = None

        for start in range(0, shard_entry.row_count, self._batch_size):
            count = min(self._batch_size, shard_entry.row_count - start)

            if effective_columns is None:
                rows, effective_columns = await self._probe_and_read(
                    shard_entry.uri, start, count
                )
            else:
                rows = await self._reader.read_row_batch(
                    shard_entry.uri,
                    start,
                    count,
                    self._artifact_storage,
                    columns=effective_columns,
                )

            if not rows:
                continue

            batch_results = await self._infer_batch(
                rows=rows,
                shard_index=shard_entry.shard_index,
                batch_start=start,
                model=model,
                model_bytes=model_bytes,
                model_metadata=model_metadata,
                label_space=label_space,
                target=target,
                prompt=prompt,
                dataset_id=dataset_id,
            )
            all_results.extend(batch_results)

        # Write prediction Parquet for this shard
        shard_uri = await self._write_prediction_shard(
            results=all_results,
            dataset_id=dataset_id,
            org_id=org_id,
            shard_index=shard_entry.shard_index,
            job_id=job_id,
        )

        return SparsePredictionShard(
            shard_uri=shard_uri,
            shard_index=shard_entry.shard_index,
            model_id=model.id,
            model_version=model_version,
            results=all_results,
        )

    # ------------------------------------------------------------------
    # schema probing (v2 embedded images vs v1 legacy columns)
    # ------------------------------------------------------------------

    async def _probe_and_read(
        self, shard_uri: str, start: int, count: int
    ) -> tuple[list[dict[str, object]], list[str]]:
        """Probe shard schema once and return (rows, effective_columns).

        Tries v2 columns ``["sample_id", "images"]`` first.  Falls back
        to v1 columns ``["sample_id", "image_uris", "metadata"]`` when
        the v2 ``images`` column is absent.
        """
        try:
            rows = await self._reader.read_row_batch(
                shard_uri,
                start,
                count,
                self._artifact_storage,
                columns=self._V2_COLUMNS,
            )
            return rows, self._V2_COLUMNS
        except (ValueError, KeyError, OSError):
            logger.info(
                "Shard %s does not have v2 'images' column — "
                "falling back to legacy v1 columns",
                shard_uri,
            )
            rows = await self._reader.read_row_batch(
                shard_uri,
                start,
                count,
                self._artifact_storage,
                columns=self._V1_COLUMNS,
            )
            return rows, self._V1_COLUMNS

    # ------------------------------------------------------------------
    # inference call (one bounded batch)
    # ------------------------------------------------------------------

    async def _infer_batch(
        self,
        *,
        rows: list[dict[str, object]],
        shard_index: int,
        batch_start: int,
        model,
        model_bytes: bytes,
        model_metadata: dict,
        label_space: list[str],
        target: str,
        prompt: str | None,
        dataset_id: str,
    ) -> list[SparsePredictionResult]:
        """Send one bounded batch to the GPU inference worker.

        Returns one :class:`SparsePredictionResult` per input row, preserving
        the row ordering.
        """
        # Build sample payloads (image bytes fetched on-demand per batch)
        samples: list[dict] = []
        for row in rows:
            sample_id = str(row.get("sample_id", f"{shard_index}:{batch_start}"))
            images_list = row.get("images")
            if images_list and find_images_by_role is not None:
                sample = self._build_v2_sample(row, sample_id, prompt or "")
            else:
                image_bytes = await self._fetch_image_bytes(row)
                sample = {
                    "sample_id": sample_id,
                    "image_bytes": image_bytes,
                    "metadata": self._parse_json_column(row.get("metadata", {})),
                    "image_uris": self._parse_image_uris(row),
                    "question": prompt or "",
                    "text": None,
                }
            samples.append(sample)

        try:
            # GPU worker client removed — inference should be dispatched via
            # Prefect flow (see T14 predict_job rewrite).
            raise NotImplementedError(
                "Sparse prediction inference requires Prefect flow dispatch"
            )
        except Exception as exc:
            logger.exception(
                "Inference batch failed: shard=%d offset=%d count=%d: %s",
                shard_index,
                batch_start,
                len(rows),
                exc,
            )
            # Capture every row as an error so the caller sees partial progress.
            return [
                SparsePredictionResult(
                    locator=SampleLocator(
                        dataset_id=dataset_id,
                        shard_index=shard_index,
                        row_index=batch_start + i,
                    ),
                    predicted_label="",
                    error=f"Inference failed: {exc}",
                )
                for i in range(len(rows))
            ]

    # ------------------------------------------------------------------
    # storage write helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_prediction_prefix(dataset_id: str, org_id: str, job_id: str) -> str:
        return f"datasets/{org_id}/{dataset_id}/predictions/{job_id}"

    async def _write_prediction_shard(
        self,
        *,
        results: list[SparsePredictionResult],
        dataset_id: str,
        org_id: str,
        shard_index: int,
        job_id: str,
    ) -> str:
        """Write prediction results as a single Parquet file and return the URI."""
        if not results:
            table = pa.table(
                {
                    "shard_index": pa.array([], type=pa.int32()),
                    "row_index": pa.array([], type=pa.int32()),
                    "dataset_id": pa.array([], type=pa.string()),
                    "predicted_label": pa.array([], type=pa.string()),
                    "confidence": pa.array([], type=pa.float64()),
                    "all_scores": pa.array([], type=pa.string()),
                    "error": pa.array([], type=pa.string()),
                }
            )
        else:
            # Serialize all_scores as JSON string (parquet has no map type).
            table = pa.table(
                {
                    "shard_index": pa.array(
                        [r.locator.shard_index for r in results],
                        type=pa.int32(),
                    ),
                    "row_index": pa.array(
                        [r.locator.row_index for r in results],
                        type=pa.int32(),
                    ),
                    "dataset_id": pa.array(
                        [dataset_id] * len(results), type=pa.string()
                    ),
                    "predicted_label": pa.array(
                        [r.predicted_label for r in results],
                        type=pa.string(),
                    ),
                    "confidence": pa.array(
                        [r.confidence for r in results], type=pa.float64()
                    ),
                    "all_scores": pa.array(
                        [
                            json.dumps(r.all_scores) if r.all_scores else None
                            for r in results
                        ],
                        type=pa.string(),
                    ),
                    "error": pa.array([r.error for r in results], type=pa.string()),
                }
            )

        buf = io.BytesIO()
        pq.write_table(table, buf)
        buf.seek(0)

        object_name = (
            f"{self._get_prediction_prefix(dataset_id, org_id, job_id)}"
            f"/{shard_index:06d}.parquet"
        )
        uri = await self._artifact_storage.put_bytes(
            object_name=object_name,
            data=buf.read(),
            content_type="application/octet-stream",
        )
        logger.debug(
            "Wrote prediction shard %d (%d rows) → %s",
            shard_index,
            len(results),
            uri,
        )
        return uri

    async def _write_job_result(
        self,
        job_result: SparsePredictionJobResult,
        dataset_id: str,
        org_id: str,
    ) -> None:
        """Persist a lightweight job result manifest to object storage.

        Only shard *metadata* is written — the per-row prediction results
        live in the per-shard Parquet files.  This keeps ``job_result.json``
        small and avoids unbounded in-memory deserialization during readback.
        """
        key = (
            f"{self._get_prediction_prefix(dataset_id, org_id, job_result.job_id)}"
            f"/job_result.json"
        )
        manifest: dict[str, object] = {
            "job_id": job_result.job_id,
            "dataset_id": job_result.dataset_id,
            "model_id": job_result.model_id,
            "model_version": job_result.model_version,
            "total_processed": job_result.total_processed,
            "total_successful": job_result.total_successful,
            "created_at": job_result.created_at.isoformat(),
            "shards": [
                {
                    "shard_uri": s.shard_uri,
                    "shard_index": s.shard_index,
                    "row_count": len(s.results),
                    "model_id": s.model_id,
                    "model_version": s.model_version,
                }
                for s in job_result.shards
            ],
        }
        data = json.dumps(manifest, indent=2).encode("utf-8")
        await self._artifact_storage.put_bytes(
            object_name=key,
            data=data,
            content_type="application/json",
        )
        logger.info("Wrote job_result.json for job %s", job_result.job_id)

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    async def _fetch_image_bytes(self, row: dict[str, object]) -> bytes | None:
        """Extract the first usable image URI from a sparse row and fetch bytes."""
        image_uris = self._parse_image_uris(row)
        if not image_uris:
            return None
        uri = image_uris[0]
        try:
            return await self._artifact_storage.get_bytes(uri)
        except (FileNotFoundError, KeyError, ValueError, OSError) as exc:
            logger.debug("Failed to fetch image bytes for %s: %s", uri, exc)
            return None

    # ── v2 embedded image helpers ─────────────────────────────────────

    @staticmethod
    def _build_v2_sample(
        row: dict[str, object],
        sample_id: str,
        question: str,
    ) -> dict[str, object]:
        """Build a sample payload from a v2 shard row with embedded images.

        Extracts review image bytes directly from the ``images``
        list<struct> column and encodes patch images as ``data:`` URIs
        in the metadata dict so the SC predictor can decode them without
        S3 fetches.
        """
        assert find_images_by_role is not None, (
            "find_images_by_role must be available for v2 prediction"
        )
        images_list = cast("list[dict[str, object]]", row.get("images", []))

        review_imgs = find_images_by_role(images_list, "review")
        image_bytes: bytes | None = (
            cast("bytes", review_imgs[0]["bytes"]) if review_imgs else None
        )

        patch_template_imgs = find_images_by_role(images_list, "patch_template")
        patch_defective_imgs = find_images_by_role(images_list, "patch_defective")

        metadata: dict[str, object] = {}
        if patch_template_imgs or patch_defective_imgs:
            patch_images: dict[str, object] = {}
            metadata["patch_images"] = patch_images
            if patch_template_imgs:
                patch_images["template"] = {
                    "image_url": _encode_data_uri(patch_template_imgs[0]),
                }
            if patch_defective_imgs:
                patch_images["defective"] = {
                    "image_url": _encode_data_uri(patch_defective_imgs[0]),
                }

        return {
            "sample_id": sample_id,
            "image_bytes": image_bytes,
            "metadata": metadata,
            "image_uris": [],
            "question": question,
            "text": None,
        }

    # ── column helpers ────────────────────────────────────────────────

    @staticmethod
    def _parse_image_uris(row: dict[str, object]) -> list[str]:
        """Parse ``image_uris`` from a Parquet row.

        The column is stored as a JSON string (``pa.string()``) in the
        SC sparse schema.  Returns an empty list for missing / unparseable
        values.
        """
        raw = row.get("image_uris")
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(u) for u in raw]
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(u) for u in parsed]
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    @staticmethod
    def _parse_json_column(value: object) -> dict[str, object]:
        """Parse a JSON-string column (e.g. ``metadata``) into a dict."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        return {}
