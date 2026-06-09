from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from app.modules.sc.models import InspectionSummary
from app.shared.api.schemas import Annotation, DatasetStorageMode
from platform_runtime.sparse import DatasetPayloadStore

if TYPE_CHECKING:
    from app.modules.sc.adapter.batch_reader import ScBatchReader


@runtime_checkable
class ScSampleListProvider(Protocol):
    """Minimal protocol for providers that can list samples by page.

    This is intentionally narrower than the canonical
    ``DatasetReader`` (:mod:`app.modules.datasets.port.dataset_reader`)
    — it only requires ``list_samples`` with keyword-only args,
    suitable for call sites that only need paginated iteration.
    """

    async def list_samples(
        self, dataset_id: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list, int]: ...


@runtime_checkable
class ScDatasetReader(ScSampleListProvider, Protocol):
    """SC-specific reader protocol that extends ``ScSampleListProvider``.

    Semantically similar to the canonical
    :class:`app.modules.datasets.port.dataset_reader.DatasetReader`,
    but with SC-specific differences:

    * ``create_annotation`` accepts an extra ``dataset_id`` keyword arg
      so the sparse-aware implementation can dispatch to the correct
      storage backend.
    * ``get_dataset`` returns ``Any | None`` (not ``Dataset | None``)
      to accommodate raw-dict returns from SC storage adapters.
    * ``list_samples`` is inherited from ``ScSampleListProvider`` with
      keyword-only args (``*``) rather than positional defaults.

    These are **intentional** — the canonical ``DatasetReader`` is not
    a drop-in replacement because callers in the SC module rely on the
    ``dataset_id`` parameter of ``create_annotation``.
    """

    async def get_dataset(
        self, dataset_id: str, org_id: str | None = None
    ) -> Any | None: ...

    async def create_annotation(
        self, annotation: Annotation, *, dataset_id: str | None = None
    ) -> Annotation: ...


class ScDatasetStore:
    dataset_model: type = InspectionSummary

    def __init__(
        self,
        dataset_payload_store: DatasetPayloadStore | None = None,
        batch_reader: ScBatchReader | None = None,
    ) -> None:
        self._payload_store = dataset_payload_store
        self._batch_reader = batch_reader

    async def map_defect_ids_to_sample_ids(
        self,
        storage: ScDatasetReader,
        dataset_id: str,
        defect_ids: set[str],
        org_id: str,
    ) -> dict[str, str]:
        """Map defect_id → sample_id.

        For ``db_full`` datasets, reads sample metadata via polars batch
        reader (fast) or scans in batches (fallback).
        For ``file_shard_sparse`` datasets, uses the manifest
        ``sample_index`` for O(1) lookups.
        """
        # ── Check storage mode ──────────────────────────────────────
        ds = await storage.get_dataset(dataset_id, org_id=org_id)
        if ds is not None and hasattr(ds, "storage_mode"):
            raw_mode = ds.storage_mode
            if isinstance(raw_mode, DatasetStorageMode):
                mode = raw_mode
            else:
                mode = DatasetStorageMode(str(raw_mode))
        else:
            mode = DatasetStorageMode.FILE_SHARD_SPARSE

        if mode == DatasetStorageMode.FILE_SHARD_SPARSE:
            return await self._map_via_sample_index(
                dataset_id=dataset_id,
                defect_ids=defect_ids,
                org_id=org_id,
            )

        # ── db_full path ────────────────────────────────────────────
        if self._batch_reader is not None:
            return await self._map_via_batch_reader(
                dataset_id=dataset_id,
                defect_ids=defect_ids,
            )

        BATCH_SIZE = 500
        offset = 0
        mapping: dict[str, str] = {}
        remaining = set(defect_ids)
        while remaining and offset < 200_000:
            samples_raw, total = await storage.list_samples(
                dataset_id, offset=offset, limit=BATCH_SIZE
            )
            if not samples_raw:
                break
            for s in samples_raw:
                platform_id = str(
                    getattr(s, "id", "") if not isinstance(s, dict) else s.get("id", "")
                )
                meta_raw = (
                    getattr(s, "metadata", getattr(s, "metadata_json", {}))
                    if not isinstance(s, dict)
                    else s.get("metadata", {})
                )
                defect_id = (
                    str((meta_raw or {}).get("defect_id", ""))
                    if isinstance(meta_raw, dict)
                    else ""
                )
                if defect_id and defect_id in remaining:
                    mapping[defect_id] = platform_id
                    remaining.discard(defect_id)
                    if not remaining:
                        return mapping
            offset += len(samples_raw)
            if offset >= total:
                break
        return mapping

    async def _map_via_batch_reader(
        self,
        *,
        dataset_id: str,
        defect_ids: set[str],
    ) -> dict[str, str]:
        """Use polars batch reader to map defect_id → sample_id in one pass."""
        if self._batch_reader is None:
            return {}
        rows = await self._batch_reader.list_all_sample_ids_meta(dataset_id)
        mapping: dict[str, str] = {}
        for row in rows:
            meta = row.get("metadata_json")
            if not isinstance(meta, dict):
                continue
            did = meta.get("defect_id")
            if isinstance(did, str) and did in defect_ids:
                sid = row.get("id")
                if isinstance(sid, str):
                    mapping[did] = sid
                    if len(mapping) == len(defect_ids):
                        break
        return mapping

    async def _map_via_sample_index(
        self,
        *,
        dataset_id: str,
        defect_ids: set[str],
        org_id: str,
    ) -> dict[str, str]:
        """Use manifest ``sample_index`` to map defect_id → sample_id.

        SC sparse manifests are keyed by upstream defect id because shard
        lookup and ``annotated_only`` filtering use that identity. Keep the
        annotation sample key aligned with the manifest key here; view/training
        bridges translate to platform ``sample_id`` where needed.
        """
        if self._payload_store is None:
            raise RuntimeError(
                "DatasetPayloadStore not available for sparse dataset lookup"
            )

        try:
            manifest = await self._payload_store.get_manifest(dataset_id, org_id)
        except Exception:
            # Manifest not found or inaccessible → empty mapping
            return {}

        index = manifest.sample_index
        mapping: dict[str, str] = {}
        for did in defect_ids:
            locator = index.get(did)
            if locator is not None:
                # TODO: remove — SC compat bridge. Sparse SC annotation keys
                # intentionally remain defect-id keyed to match manifest lookup.
                mapping[did] = did
        return mapping
