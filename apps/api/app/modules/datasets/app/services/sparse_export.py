"""Sparse export assembler — Phase 2 implementation (T19).

Streams over original dataset shards, joins annotations and prediction
results via ``manifest.sample_index``, and returns / persists an export
payload containing prediction fields (``predicted_label``, ``confidence``,
``all_scores``).

Key properties
--------------
* **Streaming shard reads** — processes one shard at a time; never loads
  all 100 k rows into memory.
* **Column projection** — reads only the columns needed for export output.
* **Graceful degradation** — handles missing annotations, missing
  prediction results, and partial prediction coverage without crashing.
"""

from __future__ import annotations

import io as _io
import json as _json
import logging
from typing import TYPE_CHECKING

import pyarrow.parquet as _pq
from sqlalchemy import select

from app.modules.sc.schema import find_images_by_role
from app.shared.db.registry import AnnotationORM
from app.modules.storage.domain.sparse import DatasetPayloadStore, SparseManifestReader

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.shared.api.schemas import Dataset
    from app.shared.domain.protocols import ArtifactStorage

logger = logging.getLogger(__name__)

_SPARSE_EXPORT_COLUMNS = ["sample_id", "image_uris", "metadata"]
"""Columns read from Parquet shards during export assembly (v1)."""

_SPARSE_EXPORT_COLUMNS_V2 = ["sample_id", "images"]
"""Columns read from v2 shards — sample_id + embedded image list<struct>."""

_FINAL_PREDICTION_DIR = "final"
_ACCUMULATED_PREDICTION_FILE = "accumulated.parquet"


class SparseExportAssembler:
    """Assembles a sparse dataset export by joining shard rows, annotations,
    and prediction results.

    Constructor dependencies are all infrastructure-level — no domain
    service coupling, consistent with the project DI pattern.
    """

    def __init__(
        self,
        *,
        store: DatasetPayloadStore,
        reader: SparseManifestReader,
        storage: ArtifactStorage,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._store = store
        self._reader = reader
        self._storage = storage
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # public entry points
    # ------------------------------------------------------------------

    async def assemble(
        self,
        dataset: Dataset,
        org_id: str,
    ) -> dict:
        """Build an in-memory export dict for the dataset.

        Returns a dict with ``format``, ``dataset``, and ``samples``.
        Each sample row includes annotation and/or prediction fields
        when available.
        """
        dataset_id = dataset.id

        # ── 1. load manifest ──────────────────────────────────────────
        try:
            manifest = await self._store.get_manifest(dataset_id, org_id)
        except FileNotFoundError:
            return self._empty_export(dataset)

        if not manifest.shards:
            return self._empty_export(dataset)

        # ── 2. load annotations from DB ───────────────────────────────
        ann_label_by_sample: dict[str, str] = await self._load_annotations(
            manifest_sample_keys=list(manifest.sample_index.keys())
            if manifest.sample_index
            else [],
        )

        # ── 3. load accumulated final prediction results ──────────────
        pred_by_sample: dict[str, dict] = await self._load_prediction_results(
            dataset_id, org_id
        )

        # ── 4. stream shards, join, assemble rows ─────────────────────
        shards_sorted = sorted(manifest.shards, key=lambda s: s.shard_index)

        is_v2 = manifest.schema_version == "v2"
        columns = _SPARSE_EXPORT_COLUMNS_V2 if is_v2 else _SPARSE_EXPORT_COLUMNS
        export_format = "sparse-export-v2" if is_v2 else "sparse-export-v1"

        samples: list[dict] = []

        for shard_entry in shards_sorted:
            if shard_entry.row_count == 0:
                continue

            rows = await self._reader.read_row_batch(
                shard_entry.uri,
                0,
                shard_entry.row_count,
                self._storage,
                columns=columns,
            )

            for row_index, row in enumerate(rows):
                sample_id = str(row.get("sample_id", ""))

                # ── annotation join ───────────────────────────────
                label = ann_label_by_sample.get(sample_id)

                # ── prediction join ───────────────────────────────
                pred = pred_by_sample.get(sample_id)

                if is_v2:
                    sample_row = self._assemble_v2_row(
                        row=row,
                        dataset_id=dataset_id,
                        sample_id=sample_id,
                    )
                else:
                    sample_row: dict = {
                        "sample_id": sample_id,
                        "defect_id": sample_id,
                        "image_uri": self._first_image_uri(row),
                        "defective_uri": self._extract_defective_uri(row),
                        "reference_uri": self._extract_reference_uri(row),
                        "metadata": self._parse_json_column(row.get("metadata", {})),
                    }

                if label is not None:
                    sample_row["label"] = label

                if pred is not None:
                    sample_row["predicted_label"] = pred.get("predicted_label", "")
                    sample_row["confidence"] = pred.get("confidence")
                    sample_row["all_scores"] = pred.get("all_scores")
                    if pred.get("error"):
                        sample_row["prediction_error"] = pred["error"]

                samples.append(sample_row)

        return {
            "format": export_format,
            "dataset": dataset.model_dump(mode="json"),
            "samples": samples,
        }

    async def assemble_and_persist(
        self,
        dataset: Dataset,
        org_id: str,
    ) -> str:
        """Assemble the export *and* persist it to object storage.

        Returns the storage URI of the persisted export artifact.
        """
        payload = await self.assemble(dataset, org_id)
        object_name = f"exports/{dataset.id}/sparse-export.json"
        uri = await self._storage.put_bytes(
            object_name=object_name,
            data=_json.dumps(payload, indent=2, default=str).encode("utf-8"),
            content_type="application/json",
        )
        logger.info(
            "Persisted sparse export for dataset %s → %s",
            dataset.id,
            uri,
        )
        return uri

    # ------------------------------------------------------------------
    # annotation loading
    # ------------------------------------------------------------------

    async def _load_annotations(
        self, manifest_sample_keys: list[str]
    ) -> dict[str, str]:
        """Query ``AnnotationORM`` for the given sample_ids.

        Returns ``{sample_id: label}`` — only the earliest label per
        sample is kept (annotations ordered by ``created_at``).

        If the manifest has no sample_index keys the result is empty.
        """
        if not manifest_sample_keys:
            return {}

        ann_label: dict[str, str] = {}
        batch_size = 500
        async with self._session_factory() as session:
            for i in range(0, len(manifest_sample_keys), batch_size):
                batch_keys = manifest_sample_keys[i : i + batch_size]
                stmt = (
                    select(AnnotationORM)
                    .where(AnnotationORM.sample_id.in_(batch_keys))
                    .order_by(AnnotationORM.created_at)
                )
                rows = (await session.execute(stmt)).scalars().all()
                for r in rows:
                    ann_label.setdefault(r.sample_id, r.label)

        logger.debug(
            "SparseExportAssembler: loaded %d annotations for %d sample_index keys",
            len(ann_label),
            len(manifest_sample_keys),
        )
        return ann_label

    # ------------------------------------------------------------------
    # prediction loading
    # ------------------------------------------------------------------

    async def _load_prediction_results(
        self, dataset_id: str, org_id: str
    ) -> dict[str, dict]:
        """Load accumulated final sparse prediction results.

        Returns ``{sample_id: {predicted_label, ...}}``.

        Returns an empty dict when no completed prediction file exists.
        """
        prefix = f"datasets/{org_id}/{dataset_id}/predictions/{_FINAL_PREDICTION_DIR}/"
        uris = await self._storage.list_prefix(prefix)
        accumulated_uris = [
            uri
            for uri in uris
            if uri.rsplit("/", 1)[-1] == _ACCUMULATED_PREDICTION_FILE
        ]
        return await self._load_accumulated_prediction_parquet(accumulated_uris)

    async def _load_accumulated_prediction_parquet(
        self, uris: list[str]
    ) -> dict[str, dict]:
        """Load accumulated final prediction rows keyed by sample_id."""
        result: dict[str, dict] = {}
        for uri in uris:
            if not uri.endswith(".parquet"):
                continue

            parquet_bytes = await self._storage.get_bytes(uri)

            table = _pq.read_table(_io.BytesIO(parquet_bytes))
            col = table.column

            sample_ids: list[str] = (
                col("sample_id").to_pylist()
                if "sample_id" in table.column_names
                else [""] * table.num_rows
            )
            pred_labels: list[str] = (
                col("predicted_label").to_pylist()
                if "predicted_label" in table.column_names
                else [""] * table.num_rows
            )
            confidences: list[float | None] = (
                col("confidence").to_pylist()
                if "confidence" in table.column_names
                else [None] * table.num_rows
            )
            all_scores_raw: list[str | None] = (
                col("all_scores").to_pylist()
                if "all_scores" in table.column_names
                else [None] * table.num_rows
            )
            errors: list[str | None] = (
                col("error").to_pylist()
                if "error" in table.column_names
                else [None] * table.num_rows
            )

            for i in range(table.num_rows):
                sample_id = str(sample_ids[i] or "")
                if not sample_id:
                    continue

                scores: dict[str, float] | None = None
                raw_scores = all_scores_raw[i]
                if isinstance(raw_scores, str) and raw_scores:
                    try:
                        scores = _json.loads(raw_scores)
                    except (_json.JSONDecodeError, TypeError):
                        pass

                result[sample_id] = {
                    "predicted_label": str(pred_labels[i] or ""),
                    "confidence": (
                        float(confidences[i]) if confidences[i] is not None else None  # type: ignore[arg-type]
                    ),
                    "all_scores": scores,
                }
                if errors[i]:
                    result[sample_id]["error"] = str(errors[i])

        return result

    # ------------------------------------------------------------------
    # v2 embedded-image helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _assemble_v2_row(
        *,
        row: dict[str, object],
        dataset_id: str,
        sample_id: str,
    ) -> dict:
        """Build an export row dict from a v2 shard row.

        Strips raw image bytes and upstream URIs.  Produces compact
        structured references with API access URLs.
        """
        images_list = SparseExportAssembler._parse_images_column(row.get("images"))

        # Build compact image references (no bytes, no source_uri).
        image_refs = SparseExportAssembler._build_image_refs_v2(
            images_list, dataset_id, sample_id
        )

        # Derive primary fields from role-matched images.
        review_imgs = find_images_by_role(images_list, "review")
        defective_imgs = find_images_by_role(images_list, "patch_defective")
        reference_imgs = find_images_by_role(images_list, "patch_template")

        sample_row: dict = {
            "sample_id": sample_id,
            "defect_id": sample_id,
            "image_uri": (
                SparseExportAssembler._make_sample_image_url(
                    dataset_id, sample_id, str(review_imgs[0]["image_id"])
                )
                if review_imgs
                else None
            ),
            "defective_uri": (
                SparseExportAssembler._make_sample_image_url(
                    dataset_id, sample_id, str(defective_imgs[0]["image_id"])
                )
                if defective_imgs
                else None
            ),
            "reference_uri": (
                SparseExportAssembler._make_sample_image_url(
                    dataset_id, sample_id, str(reference_imgs[0]["image_id"])
                )
                if reference_imgs
                else None
            ),
            "metadata": {},  # v2 has no metadata column
            "images": image_refs,
        }
        return sample_row

    @staticmethod
    def _build_image_refs_v2(
        images_list: list[dict[str, object]],
        dataset_id: str,
        sample_id: str,
    ) -> list[dict[str, object]]:
        """Convert v2 image structs into compact export references.

        Strips ``bytes`` and ``source_uri`` (upstream S3 URLs).
        Adds an ``access_url`` derived from sample identity.
        """
        refs: list[dict[str, object]] = []
        for img in images_list:
            image_id = str(img.get("image_id", ""))
            refs.append(
                {
                    "image_id": image_id,
                    "image_type": str(img.get("image_type", "")),
                    "role": str(img.get("role", "")),
                    "content_type": str(img.get("content_type", "")),
                    "filename": str(img.get("filename", "")),
                    "access_url": SparseExportAssembler._make_sample_image_url(
                        dataset_id, sample_id, image_id
                    ),
                }
            )
        return refs

    @staticmethod
    def _make_sample_image_url(dataset_id: str, sample_id: str, image_id: str) -> str:
        """Build a storage-relative API access URL for a sample image.

        Uses sample identity (sample_id + image_id), not upstream
        object-store URIs.
        """
        return f"/api/v1/datasets/{dataset_id}/samples/{sample_id}/images/{image_id}"

    @staticmethod
    def _parse_images_column(value: object) -> list[dict[str, object]]:
        """Parse the ``images`` column value into a list of dicts.

        Handles both PyArrow list-typed and plain Python list inputs.
        """
        if value is None:
            return []
        if isinstance(value, list):
            return [dict(img) if isinstance(img, dict) else {} for img in value]
        return []

    # ------------------------------------------------------------------
    # static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_export(dataset: Dataset) -> dict:
        """Return a minimal export with no sample rows."""
        return {
            "format": "sparse-export-v1",
            "dataset": dataset.model_dump(mode="json"),
            "samples": [],
        }

    @staticmethod
    def _first_image_uri(row: dict[str, object]) -> str | None:
        raw = row.get("image_uris")
        if raw is None:
            return None
        if isinstance(raw, list):
            return str(raw[0]) if raw else None
        if isinstance(raw, str):
            try:
                parsed = _json.loads(raw)
                if isinstance(parsed, list) and parsed:
                    return str(parsed[0])
            except (_json.JSONDecodeError, TypeError):
                pass
        return None

    @staticmethod
    def _extract_defective_uri(row: dict[str, object]) -> str | None:
        """Extract the first review image URL from metadata."""
        meta = SparseExportAssembler._parse_json_column(row.get("metadata", {}))
        review_images = meta.get("review_images", [])
        if isinstance(review_images, list) and review_images:
            first = review_images[0]
            if isinstance(first, dict):
                url = first.get("image_url")
                if url:
                    return str(url)
        return None

    @staticmethod
    def _extract_reference_uri(row: dict[str, object]) -> str | None:
        """Extract the template (patch) image URL from metadata."""
        meta = SparseExportAssembler._parse_json_column(row.get("metadata", {}))
        patch_images = meta.get("patch_images", {})
        if isinstance(patch_images, dict):
            template = patch_images.get("template", {})
            if isinstance(template, dict):
                url = template.get("image_url")
                if url:
                    return str(url)
        return None

    @staticmethod
    def _parse_json_column(value: object) -> dict[str, object]:
        """Parse a JSON-string column (e.g. ``metadata``) into a dict."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = _json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (_json.JSONDecodeError, TypeError):
                pass
        return {}
