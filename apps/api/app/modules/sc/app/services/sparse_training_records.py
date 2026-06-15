"""Sparse training record schema and assembler for ``resnet50-sc-v1``.

Defines the training record contract that the SC trainer consumes and an
assembler that reads only needed columns from sparse Parquet shards via
column projection, grouped by shard/index to avoid per-annotation scans.

This module lives on the **API side** — kept importable by worker-side
sparse loaders (T11) without pulling in ``apps.api`` internals.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.modules.sc.schema import (
    SC_SOURCE_SCHEMA_VERSION,
    find_images_by_role,
)
from platform_runtime.contracts import ArtifactStorage
from platform_runtime.sparse import (
    DatasetManifest,
    DatasetPayloadStore,
    SampleLocator,
    SparseManifestReader,
)

if TYPE_CHECKING:
    from app.shared.api.schemas import Annotation

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sparse training record schema
# ---------------------------------------------------------------------------

_PARQUET_COLUMNS_FOR_TRAINING = ["sample_id", "image_uris", "metadata", "images"]
"""Columns that may be projected from sparse shards during record assembly.

Avoids fetching defect_id, inspection_time, wafer_*, rough_bin,
class_number, lot_id — fields the SC trainer does not consume.

For SC v2 shards (schema_version=``"v2"``) only ``sample_id`` and
``images`` are projected — ``image_uris`` and ``metadata`` do not exist
in the v2 schema.  For legacy / v1 shards, ``images`` is excluded from
the projection at read time (see :meth:`_read_training_columns`).
"""


class SparseTrainingRecord(BaseModel):
    """Canonical training record shape for the SC sparse training path.

    Mirrors the record shape produced by
    :func:`~app.modules.training.flows.train_job.load_dataset_records`
    for ``db_full`` datasets so that ``resnet50-sc-v1`` (and any future
    dual-view SC trainer) can consume records from either path without
    branching on storage mode.
    """

    sample_id: str
    """Logical sample identity — the ``defect_id`` in sparse mode."""

    label: str
    """Human annotation label (e.g. ``"defect"``, ``"clean"``)."""

    image_uri: str = ""
    """Primary image URI (first entry from the ``image_uris`` column)."""

    defective_uri: str = ""
    """Defective patch image URL extracted from ``review_images[0].image_url``."""

    reference_uri: str = ""
    """Reference / template image URL from ``patch_images.template.image_url``."""

    defective_bytes: bytes | None = None
    """Defective patch image bytes embedded in SC v2 shards (``images`` column).

    ``None`` for legacy / v1 shards where image data is accessed via URIs
    instead of embedded bytes.
    """

    reference_bytes: bytes | None = None
    """Reference / template image bytes embedded in SC v2 shards (``images`` column).

    ``None`` for legacy / v1 shards where image data is accessed via URIs
    instead of embedded bytes.
    """

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Raw row metadata (deserialised ``metadata`` JSON column).
    Available for downstream consumers that need inspection context.

    For SC v2 shards this is an empty dict — no ``metadata`` column
    exists in the v2 schema.
    """


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------


class SparseTrainingRecordAssembler:
    """Assembles :class:`SparseTrainingRecord` objects from sparse shards
    and platform annotations.

    Usage::

        assembler = SparseTrainingRecordAssembler(
            manifest_reader=SparseManifestReader(),
            payload_store=payload_store,
        )
        records = await assembler.assemble(
            dataset_id="ds-1",
            org_id="org-1",
            annotations=annotations,
            storage=artifact_storage,
        )
    """

    def __init__(
        self,
        *,
        manifest_reader: SparseManifestReader,
        payload_store: DatasetPayloadStore,
    ) -> None:
        self._reader = manifest_reader
        self._payload_store = payload_store

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    async def assemble(
        self,
        *,
        dataset_id: str,
        org_id: str,
        annotations: list[Annotation],
        storage: ArtifactStorage,
    ) -> list[SparseTrainingRecord]:
        """Produce training records from sparse shards joined with annotations.

        Parameters
        ----------
        dataset_id : str
            Platform dataset identifier.
        org_id : str
            Organization UUID used to locate the manifest in object storage.
        annotations : list[Annotation]
            Platform annotation objects (already filtered to *dataset_id*).
        storage : ArtifactStorage
            Must satisfy the :class:`~platform_runtime.contracts.ArtifactStorage`
            protocol — ``get_bytes(uri) -> bytes`` is sufficient.

        Returns
        -------
        list[SparseTrainingRecord]
            Assembled records.  Empty when there are zero annotations or
            the manifest is missing / has no matching entries.
        """
        # ── Guard: zero annotations ──────────────────────────────────
        if not annotations:
            _logger.info(
                "No annotations found for dataset_id=%s — returning empty record list",
                dataset_id,
            )
            return []

        # ── Load manifest ────────────────────────────────────────────
        try:
            manifest = await self._payload_store.get_manifest(dataset_id, org_id)
        except FileNotFoundError:
            _logger.warning(
                "Manifest not found for dataset_id=%s org_id=%s — returning empty records",
                dataset_id,
                org_id,
            )
            return []
        except Exception:
            _logger.exception(
                "Failed to load manifest for dataset_id=%s org_id=%s",
                dataset_id,
                org_id,
            )
            return []

        # ── Resolve annotations → sample_index entries ───────────────
        if not manifest.sample_index:
            _logger.info(
                "Manifest sample_index is empty for dataset_id=%s — returning empty records",
                dataset_id,
            )
            return []

        index = manifest.sample_index
        matched: dict[str, tuple[str, SampleLocator]] = {}
        for ann in annotations:
            locator = index.get(ann.sample_id)
            if locator is not None:
                matched[ann.sample_id] = (ann.label, locator)

        if not matched:
            _logger.info(
                "No annotations matched sample_index entries for dataset_id=%s "
                "(annotations=%d, index_keys=%d)",
                dataset_id,
                len(annotations),
                len(index),
            )
            return []

        # ── Group by shard_index (one read per shard) ─────────────────
        by_shard: dict[int, list[tuple[str, str, int]]] = {}
        #                    (sample_id, label, row_index)
        for sample_id, (label, locator) in matched.items():
            by_shard.setdefault(locator.shard_index, []).append(
                (sample_id, label, locator.row_index)
            )

        # ── Read needed columns per shard, join with labels ──────────
        records: list[SparseTrainingRecord] = []
        for shard_index, entries in by_shard.items():
            shard_rows = await self._read_training_columns(
                manifest, shard_index, storage
            )
            for sample_id, label, row_idx in entries:
                if row_idx < 0 or row_idx >= len(shard_rows):
                    _logger.warning(
                        "Row index %d out of range [0, %d) for sample_id=%s "
                        "shard_index=%d — skipping",
                        row_idx,
                        len(shard_rows),
                        sample_id,
                        shard_index,
                    )
                    continue
                row = shard_rows[row_idx]
                record = self._row_to_record(sample_id, label, row)
                records.append(record)

        _logger.info(
            "Assembled %d sparse training records for dataset_id=%s "
            "(annotations=%d, matched=%d, shards_read=%d)",
            len(records),
            dataset_id,
            len(annotations),
            len(matched),
            len(by_shard),
        )
        return records

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    async def _read_training_columns(
        self,
        manifest: DatasetManifest,
        shard_index: int,
        storage: ArtifactStorage,
    ) -> list[dict[str, object]]:
        """Read only the training-relevant columns for one shard.

        Projects ``sample_id`` + ``images`` for SC v2 shards; projects
        ``sample_id`` + ``image_uris`` + ``metadata`` for legacy / v1
        shards.  This avoids requesting columns that do not exist in the
        shard schema.
        """
        shard_entry = manifest.shards[shard_index]
        is_v2 = manifest.schema_version == SC_SOURCE_SCHEMA_VERSION
        # ── v2 shards: project sample_id + images only ────────────
        # ── v1 / legacy: project sample_id + image_uris + metadata
        columns = [
            c
            for c in _PARQUET_COLUMNS_FOR_TRAINING
            if (is_v2 and c in ("sample_id", "images")) or (not is_v2 and c != "images")
        ]
        return await self._reader.read_row_batch(
            shard_uri=shard_entry.uri,
            start=0,
            count=shard_entry.row_count,
            storage=storage,
            columns=columns,
        )

    @staticmethod
    def _row_to_record(
        sample_id: str, label: str, row: dict[str, object]
    ) -> SparseTrainingRecord:
        """Convert a sparse shard row + label into a training record.

        Detects SC v2 shards by the presence of an ``images`` key in the
        row and delegates to :meth:`_row_to_record_v2`; otherwise uses the
        legacy / v1 path (:meth:`_row_to_record_v1`).
        """
        if "images" in row:
            return SparseTrainingRecordAssembler._row_to_record_v2(
                sample_id, label, row
            )
        return SparseTrainingRecordAssembler._row_to_record_v1(sample_id, label, row)

    @staticmethod
    def _row_to_record_v1(
        sample_id: str, label: str, row: dict[str, object]
    ) -> SparseTrainingRecord:
        """Legacy / v1 path: extract URIs from ``image_uris`` and ``metadata`` JSON columns."""
        image_uri = ""
        defective_uri = ""
        reference_uri = ""
        meta: dict[str, Any] = {}

        image_uris_raw = row.get("image_uris", "")
        if isinstance(image_uris_raw, str) and image_uris_raw:
            try:
                uris = json.loads(image_uris_raw)
                if isinstance(uris, list) and uris:
                    image_uri = str(uris[0])
            except (json.JSONDecodeError, TypeError):
                pass

        metadata_raw = row.get("metadata", "")
        if isinstance(metadata_raw, str) and metadata_raw:
            try:
                meta = json.loads(metadata_raw)
            except (json.JSONDecodeError, TypeError):
                pass

        review_images = meta.get("review_images", [])
        if isinstance(review_images, list) and review_images:
            first_img = review_images[0]
            if isinstance(first_img, dict):
                defective_uri = str(first_img.get("image_url", ""))

        patch_images = meta.get("patch_images")
        if isinstance(patch_images, dict):
            tpl = patch_images.get("template")
            if isinstance(tpl, dict):
                reference_uri = str(tpl.get("image_url", ""))

        return SparseTrainingRecord(
            sample_id=sample_id,
            label=label,
            image_uri=image_uri,
            defective_uri=defective_uri,
            reference_uri=reference_uri,
            metadata=meta,
        )

    @staticmethod
    def _row_to_record_v2(
        sample_id: str, label: str, row: dict[str, object]
    ) -> SparseTrainingRecord:
        """SC v2 path: extract embedded bytes from ``images`` list<struct> column.

        Uses :func:`find_images_by_role` to locate review and template
        images within the ``images`` column.  URIs are intentionally left
        empty — v2 shards embed bytes directly and skip URI resolution.
        """
        images_raw: object = row.get("images")
        images_list: list[dict[str, object]] = (
            images_raw if isinstance(images_raw, list) else []
        )

        review_imgs = find_images_by_role(images_list, "review")
        template_imgs = find_images_by_role(images_list, "patch_template")
        _defective_patch_imgs = find_images_by_role(images_list, "patch_defective")

        _defective_raw = review_imgs[0].get("bytes") if review_imgs else None
        _reference_raw = template_imgs[0].get("bytes") if template_imgs else None
        defective_bytes: bytes | None = (
            _defective_raw if isinstance(_defective_raw, bytes) else None
        )
        reference_bytes: bytes | None = (
            _reference_raw if isinstance(_reference_raw, bytes) else None
        )

        image_uri = ""
        if review_imgs:
            src = review_imgs[0].get("source_uri")
            if isinstance(src, str) and src:
                image_uri = src

        return SparseTrainingRecord(
            sample_id=sample_id,
            label=label,
            image_uri=image_uri,
            defective_uri="",
            reference_uri="",
            defective_bytes=defective_bytes,
            reference_bytes=reference_bytes,
            metadata={},
        )
