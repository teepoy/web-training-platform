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

from app.modules.sc.schema import SC_SOURCE_SCHEMA_VERSION_V4, find_images_by_role
from app.modules.sc.domain.image_url import build_sc_image_url
from app.shared.db.registry import AnnotationORM
from app.modules.storage.domain.sparse import DatasetPayloadStore, SparseManifestReader

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.shared.api.schemas import Dataset
    from app.shared.domain.protocols import ArtifactStorage

logger = logging.getLogger(__name__)

_SPARSE_EXPORT_COLUMNS = ["sample_id", "image_uris", "metadata"]
"""Columns read from Parquet shards during export assembly (v1)."""

_SPARSE_EXPORT_COLUMNS_V2 = [
    "sample_id",
    "defect_id",
    "inspection_time",
    "wafer_key",
    "images",
]
"""Scalar image identity plus the v2 embedded image list<struct>."""

_SPARSE_EXPORT_COLUMNS_V4 = ["sample_id", "defect_id"]
"""Closed identity membership stored by current SC imports."""

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
            return self._empty_export(dataset, schema_version=manifest.schema_version)

        # ── 2. load annotations from DB ───────────────────────────────
        ann_label_by_sample: dict[str, str] = await self._load_annotations(
            manifest_sample_keys=list(manifest.sample_index.keys())
        )

        # ── 3. load accumulated final prediction results ──────────────
        pred_by_sample: dict[str, dict] = await self._load_prediction_results(
            dataset_id, org_id
        )

        # ── 4. stream shards, join, assemble rows ─────────────────────
        shards_sorted = sorted(manifest.shards, key=lambda s: s.shard_index)

        schema_version = manifest.schema_version
        if schema_version == SC_SOURCE_SCHEMA_VERSION_V4:
            columns = _SPARSE_EXPORT_COLUMNS_V4
            export_format = "sparse-export-v4"
            source_inspection_time, source_wafer_key = self._v4_source_identity(dataset)
        elif schema_version == "v3":
            columns = [column.name for column in manifest.schema_columns]
            if not columns:
                raise ValueError(
                    "SC v3 manifest is missing its concrete schema columns"
                )
            export_format = "sparse-export-v3"
        elif schema_version == "v2":
            columns = _SPARSE_EXPORT_COLUMNS_V2
            export_format = "sparse-export-v2"
        elif schema_version in (None, "v1"):
            columns = _SPARSE_EXPORT_COLUMNS
            export_format = "sparse-export-v1"
        else:
            raise ValueError(
                f"Unsupported sparse export schema version: {schema_version!r}"
            )

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

            if not manifest.sample_index:
                ann_label_by_sample.update(
                    await self._load_annotations(
                        [str(row.get("sample_id", "")) for row in rows]
                    )
                )

            for row_index, row in enumerate(rows):
                sample_id = str(row.get("sample_id", ""))

                # ── annotation join ───────────────────────────────
                label = ann_label_by_sample.get(sample_id)

                # ── prediction join ───────────────────────────────
                pred = pred_by_sample.get(sample_id)

                if schema_version == SC_SOURCE_SCHEMA_VERSION_V4:
                    sample_row = self._assemble_v4_row(
                        row=row,
                        dataset_id=dataset_id,
                        sample_id=sample_id,
                        inspection_time=source_inspection_time,
                        wafer_key=source_wafer_key,
                    )
                elif schema_version == "v3":
                    sample_row = self._assemble_v3_row(
                        row=row,
                        dataset_id=dataset_id,
                        sample_id=sample_id,
                    )
                elif schema_version == "v2":
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
    # versioned image helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _v4_source_identity(dataset: Dataset) -> tuple[str, int]:
        inspection_time = dataset.dataset_meta.get("source_inspection_time")
        wafer_key = dataset.dataset_meta.get("source_wafer_key")
        if not isinstance(inspection_time, str) or not inspection_time.strip():
            raise ValueError(
                f"SC Dataset {dataset.id} is missing source_inspection_time"
            )
        if not isinstance(wafer_key, int) or isinstance(wafer_key, bool):
            raise ValueError(f"SC Dataset {dataset.id} has invalid source_wafer_key")
        return inspection_time, wafer_key

    @staticmethod
    def _assemble_v4_row(
        *,
        row: dict[str, object],
        dataset_id: str,
        sample_id: str,
        inspection_time: str,
        wafer_key: int,
    ) -> dict:
        """Export identity membership without treating stored legacy fields as source."""
        identity_row = {
            "sample_id": sample_id,
            "defect_id": str(row.get("defect_id") or sample_id),
            "inspection_time": inspection_time,
            "wafer_key": wafer_key,
        }
        return SparseExportAssembler._assemble_v3_row(
            row=identity_row,
            dataset_id=dataset_id,
            sample_id=sample_id,
        )

    @staticmethod
    def _assemble_v3_row(
        *,
        row: dict[str, object],
        dataset_id: str,
        sample_id: str,
    ) -> dict:
        """Build deterministic patch references from a scalar-only v3 row."""
        image_specs = (
            ("template", "patch_template"),
            ("defective", "patch_defective"),
            ("difference", "patch_difference"),
        )
        images = [
            {
                "image_id": f"{sample_id}_{image_type}",
                "image_type": image_type,
                "role": role,
                "content_type": "image/png",
                "filename": f"{image_type}.png",
                "access_url": build_sc_image_url(
                    inspection_time=row.get("inspection_time"),
                    wafer_key=row.get("wafer_key"),
                    defect_id=row.get("defect_id") or sample_id,
                    image_type=image_type,
                ),
            }
            for image_type, role in image_specs
        ]
        by_role = {str(image["role"]): image for image in images}
        return {
            "sample_id": sample_id,
            "defect_id": str(row.get("defect_id") or sample_id),
            "image_uri": None,
            "defective_uri": by_role["patch_defective"]["access_url"],
            "reference_uri": by_role["patch_template"]["access_url"],
            "metadata": {
                key: value
                for key, value in row.items()
                if key not in ("id", "sample_id")
            },
            "images": images,
        }

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
        image_refs = SparseExportAssembler._build_image_refs_v2(images_list, row)
        refs_by_id = {str(ref["image_id"]): ref for ref in image_refs}

        # Derive primary fields from role-matched images.
        review_imgs = find_images_by_role(images_list, "review")
        defective_imgs = find_images_by_role(images_list, "patch_defective")
        reference_imgs = find_images_by_role(images_list, "patch_template")

        sample_row: dict = {
            "sample_id": sample_id,
            "defect_id": sample_id,
            "image_uri": (
                refs_by_id[str(review_imgs[0]["image_id"])]["access_url"]
                if review_imgs
                else None
            ),
            "defective_uri": (
                refs_by_id[str(defective_imgs[0]["image_id"])]["access_url"]
                if defective_imgs
                else None
            ),
            "reference_uri": (
                refs_by_id[str(reference_imgs[0]["image_id"])]["access_url"]
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
        row: dict[str, object],
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
                    "access_url": build_sc_image_url(
                        inspection_time=row.get("inspection_time"),
                        wafer_key=row.get("wafer_key"),
                        defect_id=row.get("defect_id") or row.get("sample_id"),
                        image_type=img.get("image_type") or img.get("role"),
                        review_image_id=img.get("review_image_id"),
                    ),
                }
            )
        return refs

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
    def _empty_export(
        dataset: Dataset,
        *,
        schema_version: str | None = None,
    ) -> dict:
        """Return a minimal export with no sample rows."""
        export_format = {
            None: "sparse-export-v1",
            "v1": "sparse-export-v1",
            "v2": "sparse-export-v2",
            "v3": "sparse-export-v3",
            SC_SOURCE_SCHEMA_VERSION_V4: "sparse-export-v4",
        }.get(schema_version)
        if export_format is None:
            raise ValueError(
                f"Unsupported sparse export schema version: {schema_version!r}"
            )
        return {
            "format": export_format,
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
