from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Protocol, cast

from app.modules.datasets.app.services.sparse_import_operator import (
    SparseImportOperator,
)
from app.modules.sc.domain.entities.sc_import import ScImportStatus
from app.modules.sc.domain.image_fetcher import ScImageFetcher
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.sc.app.services.import_rows import (
    _geometry_from_inspection,
    iter_patch_samples_from_upstream_chunk,
)
from app.modules.sc.schema import (
    SC_SPARSE_SHARD_SCHEMA_V2,
    _build_v2_pyarrow_schema,
)
from app.shared.api.schemas import (
    Dataset,
    DatasetStorageMode,
    SPARSE_NO_LS,
    TaskSpec,
)
from platform_runtime.sparse import (
    ColumnSchema,
    DatasetManifest,
    DatasetPayloadStore,
    SampleLocator,
    ShardEntry,
)

logger = logging.getLogger(__name__)

SC_IMPORT_BATCH_SIZE = 100_000
ScImportProgressCallback = Callable[[ScImportStatus], Awaitable[None]]


# ── SC-specific helpers ─────────────────────────────────────────────────────


def _patch_sample_to_parquet_row(
    ps: Any, images: list[dict[str, object]]
) -> dict[str, Any]:
    inspection_time_str = ""
    if ps.inspection_time is not None:
        inspection_time_str = ps.inspection_time.isoformat()

    review_images = getattr(ps, "review_images", []) or []
    has_review = 1 if review_images else 0

    return {
        "sample_id": ps.sample_id,
        "defect_id": ps.defect_id,
        "inspection_time": inspection_time_str,
        "wafer_key": ps.wafer_key,
        "wafer_x": ps.wafer_x,
        "wafer_y": ps.wafer_y,
        "die_x": ps.die_x,
        "die_y": ps.die_y,
        "rough_bin": ps.rough_bin,
        "class_number": ps.class_number,
        "lot_id": ps.lot_id,
        "has_review": has_review,
        "images": images,
    }


async def _build_image_structs(
    *,
    patch_sample: Any,
    inspection_time: Any,
    wafer_key: int,
) -> list[dict[str, object]]:
    images: list[dict[str, object]] = []
    defect_id = patch_sample.defect_id
    insp_time_str = (
        inspection_time.isoformat()
        if hasattr(inspection_time, "isoformat")
        else str(inspection_time)
    )

    review_images: list[Any] = getattr(patch_sample, "review_images", []) or []
    for review_image in review_images:
        images.append(
            {
                "image_id": str(review_image.image_id),
                "image_type": "review",
                "role": "review",
                "content_type": "image/png",
                "filename": review_image.image_name,
                "bytes": None,
                "review_image_id": review_image.image_id,
                "source_uri": (
                    f"mock-sc://review/{insp_time_str}/{wafer_key}/{defect_id}/"
                    f"{review_image.image_id}"
                ),
            }
        )

    images.append(
        {
            "image_id": f"{defect_id}_template",
            "image_type": "template",
            "role": "patch_template",
            "content_type": "image/png",
            "filename": "template.png",
            "bytes": None,
            "review_image_id": None,
            "source_uri": (
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/template.png"
            ),
        }
    )

    images.append(
        {
            "image_id": f"{defect_id}_defective",
            "image_type": "defective",
            "role": "patch_defective",
            "content_type": "image/png",
            "filename": "defective.png",
            "bytes": None,
            "review_image_id": None,
            "source_uri": (
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/defective.png"
            ),
        }
    )

    images.append(
        {
            "image_id": f"{defect_id}_difference",
            "image_type": "difference",
            "role": "patch_difference",
            "content_type": "image/png",
            "filename": "difference.png",
            "bytes": None,
            "review_image_id": None,
            "source_uri": (
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/difference.png"
            ),
        }
    )

    return images


class ScImportRepository(Protocol):
    async def create_dataset(
        self, dataset: Dataset, org_id: str | None = None
    ) -> Dataset: ...

    async def update_dataset_meta(
        self, dataset_id: str, meta_update: dict
    ) -> Dataset | None: ...


class ScImportPayloadStore(Protocol):
    async def put_manifest(self, manifest: DatasetManifest, *, org_id: str) -> str: ...


class ScImportService:
    def __init__(
        self,
        repository: ScImportRepository | None = None,
        payload_store: ScImportPayloadStore | None = None,
        upstream_reader: ScUpstreamReader | None = None,
        image_fetcher: ScImageFetcher | None = None,
    ) -> None:
        self._repo = repository
        self._payload_store = payload_store
        self._upstream = upstream_reader
        self._image_fetcher = image_fetcher

    async def submit_import(
        self,
        source_inspection_time: str,
        source_wafer_key: int,
        dataset_name: str,
        storage_mode: str,
        org_id: str,
        filters: dict | None = None,
        label_space: list[str] | None = None,
        max_rows: int | None = None,
        on_progress: ScImportProgressCallback | None = None,
    ) -> ScImportStatus:
        assert self._upstream is not None
        assert self._repo is not None
        assert self._payload_store is not None
        # ── Pre-check: skip dataset creation when upstream has no data ──
        try:
            insp_dt = datetime.fromisoformat(source_inspection_time)
            samples_lf = await self._upstream.list_samples(
                insp_dt, source_wafer_key, offset=0, count=1
            )
            samples_df = await samples_lf.collect_async()
            if len(samples_df) == 0:
                logger.info(
                    "SC import: upstream has no data for inspection_time=%s "
                    "wafer_key=%d — skipping dataset creation",
                    source_inspection_time,
                    source_wafer_key,
                )
                return ScImportStatus(
                    status="completed",
                    source_inspection_time=source_inspection_time,
                    source_wafer_key=source_wafer_key,
                    dataset_name=dataset_name,
                    storage_mode=storage_mode,
                    imported_count=0,
                )
        except Exception:
            logger.warning(
                "SC import: upstream pre-check failed — proceeding with dataset creation",
                exc_info=True,
            )

        dataset = await self._create_dataset(
            source_inspection_time=source_inspection_time,
            source_wafer_key=source_wafer_key,
            dataset_name=dataset_name,
            storage_mode=storage_mode,
            org_id=org_id,
            label_space=label_space,
        )
        if dataset is None:
            return await self._fail(
                "Failed to create dataset",
                source_inspection_time,
                source_wafer_key,
                dataset_name,
                storage_mode,
            )

        try:
            result = await self._run_direct_import(
                dataset_id=dataset.id,
                org_id=org_id,
                source_inspection_time=source_inspection_time,
                source_wafer_key=source_wafer_key,
                max_rows=max_rows,
                logger=logger,
                on_progress=on_progress,
            )
            imported_count_raw = result.get("imported_count", 0)
            imported_count: int = (
                int(imported_count_raw)
                if isinstance(imported_count_raw, (int, float))
                else 0
            )
            completed_status = ScImportStatus(
                status="completed",
                dataset_id=dataset.id,
                dataset_name=dataset_name,
                source_inspection_time=source_inspection_time,
                source_wafer_key=source_wafer_key,
                storage_mode=storage_mode,
                imported_count=imported_count,
            )
            return completed_status
        except Exception as e:
            logger.exception("Direct import failed, dataset=%s", dataset.id)
            return await self._fail(
                f"Direct import failed: {e}",
                source_inspection_time,
                source_wafer_key,
                dataset_name,
                storage_mode,
            )

    async def _run_direct_import(
        self,
        *,
        dataset_id: str,
        org_id: str,
        source_inspection_time: str,
        source_wafer_key: int,
        max_rows: int | None = None,
        logger: logging.Logger | logging.LoggerAdapter | None = None,
        on_progress: ScImportProgressCallback | None = None,
    ) -> dict[str, object]:
        """Direct sparse import that keeps request handling cooperative."""
        assert self._upstream is not None
        assert self._payload_store is not None
        _payload_store = self._payload_store
        _upstream = self._upstream
        schema_columns = [
            ColumnSchema(name=c["name"], type=c["type"])
            for c in SC_SPARSE_SHARD_SCHEMA_V2
        ]
        pyarrow_schema = _build_v2_pyarrow_schema()

        insp_dt = datetime.fromisoformat(source_inspection_time)
        if insp_dt.tzinfo is None:
            insp_dt = insp_dt.replace(tzinfo=timezone.utc)

        operator = SparseImportOperator(
            dataset_id=dataset_id,
            org_id=org_id,
            payload_store=cast(DatasetPayloadStore, _payload_store),
        )
        shard_entries: list[ShardEntry] = []
        sample_index: dict[str, SampleLocator] = {}
        total_rows = 0
        shard_count = 0
        batch_size = SC_IMPORT_BATCH_SIZE

        async def publish_manifest() -> None:
            manifest = DatasetManifest(
                dataset_id=dataset_id,
                storage_mode="file_shard_sparse",
                shard_count=shard_count,
                total_rows=total_rows,
                schema_columns=schema_columns,
                shards=shard_entries,
                sample_index=sample_index,
                schema_version="v2",
            )
            await _payload_store.put_manifest(manifest, org_id=org_id)

        async def publish_progress() -> None:
            if on_progress is None:
                return
            imported_count = total_rows + len(batch)
            await on_progress(
                ScImportStatus(
                    status="running",
                    dataset_id=dataset_id,
                    source_inspection_time=source_inspection_time,
                    source_wafer_key=source_wafer_key,
                    storage_mode="file_shard_sparse",
                    imported_count=imported_count,
                    remaining_count=max(total_rows_available - imported_count, 0),
                    dataset_name="",
                    error=None,
                )
            )

        batch: list[dict[str, Any]] = []

        lf = await _upstream.list_samples(insp_dt, source_wafer_key, count=None)
        df = await lf.collect_async()
        total_rows_available = len(df)

        if total_rows_available == 0:
            return {"dataset_id": dataset_id, "imported_count": 0, "total_available": 0}

        await publish_progress()

        indices = (
            list(range(total_rows_available))[:max_rows]
            if max_rows is not None
            else list(range(total_rows_available))
        )
        filtered_df = df[indices]

        for row_offset, patch_sample in enumerate(
            iter_patch_samples_from_upstream_chunk(filtered_df),
            start=1,
        ):
            images = await _build_image_structs(
                patch_sample=patch_sample,
                inspection_time=insp_dt,
                wafer_key=source_wafer_key,
            )
            batch.append(_patch_sample_to_parquet_row(patch_sample, images))
            if len(batch) >= batch_size:
                shard_entry, locators = await operator.flush_shard(
                    shard_index=shard_count,
                    rows=batch,
                    pyarrow_schema=pyarrow_schema,
                    row_id_key="defect_id",
                )
                shard_entries.append(shard_entry)
                sample_index.update(locators)
                total_rows += len(batch)
                shard_count += 1
                await publish_manifest()
                await publish_progress()
                batch = []
            if row_offset % 5000 == 0:
                await asyncio.sleep(0)

        if batch:
            shard_entry, locators = await operator.flush_shard(
                shard_index=shard_count,
                rows=batch,
                pyarrow_schema=pyarrow_schema,
                row_id_key="defect_id",
            )
            shard_entries.append(shard_entry)
            sample_index.update(locators)
            total_rows += len(batch)
            shard_count += 1
            await publish_manifest()
            await publish_progress()

        if shard_count == 0:
            await publish_manifest()

        if logger is not None:
            logger.info(
                "Sparse import complete: %d rows across %d shards",
                total_rows,
                shard_count,
            )

        return {
            "dataset_id": dataset_id,
            "imported_count": total_rows,
            "total_available": total_rows_available,
        }

    async def _create_dataset(
        self,
        *,
        source_inspection_time: str,
        source_wafer_key: int,
        dataset_name: str,
        storage_mode: str,
        org_id: str,
        label_space: list[str] | None,
    ) -> Dataset | None:
        assert self._repo is not None
        assert self._payload_store is not None
        assert self._upstream is not None
        try:
            dataset = Dataset(
                name=dataset_name,
                dataset_type="image_sc",
                task_spec=TaskSpec(task_type="sc", label_space=label_space or []),
                view_types=[
                    "image_input_v1",
                    "patch_image_v1",
                    "review_image_v1",
                ],
                org_id=org_id,
                ls_project_id=SPARSE_NO_LS,
                storage_mode=DatasetStorageMode(storage_mode),
            )
            dataset = await self._repo.create_dataset(dataset, org_id=org_id)
            await self._payload_store.put_manifest(
                DatasetManifest(
                    dataset_id=dataset.id,
                    storage_mode=dataset.storage_mode.value,
                    shard_count=0,
                    total_rows=0,
                ),
                org_id=org_id,
            )

            if storage_mode == "file_shard_sparse":
                insp_dt_geo = datetime.fromisoformat(source_inspection_time)
                if insp_dt_geo.tzinfo is None:
                    insp_dt_geo = insp_dt_geo.replace(tzinfo=timezone.utc)
                inspection = await self._upstream.get_inspection(
                    insp_dt_geo, source_wafer_key
                )
                if inspection is not None:
                    geometry = _geometry_from_inspection(inspection)
                    await self._repo.update_dataset_meta(
                        dataset.id, {"geometry": geometry}
                    )

            return dataset
        except Exception:
            logger.exception(
                "Failed to create dataset: %s (%s/%s)",
                dataset_name,
                source_inspection_time,
                source_wafer_key,
            )
            return None

    async def _fail(
        self,
        error_message: str,
        source_inspection_time: str = "",
        source_wafer_key: int = 0,
        dataset_name: str = "",
        storage_mode: str = "file_shard_sparse",
    ) -> ScImportStatus:
        failed_status = ScImportStatus(
            status="failed",
            error=error_message,
            source_inspection_time=source_inspection_time,
            source_wafer_key=source_wafer_key,
            dataset_name=dataset_name,
            storage_mode=storage_mode,
        )
        return failed_status
