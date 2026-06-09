from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
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

DIRECT_IMPORT_MAX_ROWS = 30000


# ── SC-specific helpers ─────────────────────────────────────────────────────


def _patch_sample_to_parquet_row(
    ps: Any, images: list[dict[str, object]]
) -> dict[str, Any]:
    inspection_time_str = ""
    if ps.inspection_time is not None:
        inspection_time_str = ps.inspection_time.isoformat()

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
        "images": images,
    }


async def _build_image_structs(
    *,
    patch_sample: Any,
    inspection_time: Any,
    wafer_key: int,
    image_fetcher: ScImageFetcher,
) -> list[dict[str, object]]:
    images: list[dict[str, object]] = []
    defect_id = patch_sample.defect_id
    insp_time_str = (
        inspection_time.isoformat()
        if hasattr(inspection_time, "isoformat")
        else str(inspection_time)
    )

    review_images: list[Any] = getattr(patch_sample, "review_images", []) or []
    review_fetches: list[tuple[Any, int]] = []

    fetches: list[Awaitable[bytes]] = []
    for review_image in review_images:
        review_fetches.append((review_image, len(fetches)))
        fetches.append(
            image_fetcher.get_image_bytes(
                inspection_time=insp_time_str,
                wafer_key=wafer_key,
                defect_id=defect_id,
                image_type="review",
                review_image_id=review_image.image_id,
            )
        )

    template_fetch_index = len(fetches)
    fetches.append(
        image_fetcher.get_image_bytes(
            inspection_time=insp_time_str,
            wafer_key=wafer_key,
            defect_id=defect_id,
            image_type="PATCH_TEMPLATE",
        )
    )
    defective_fetch_index = len(fetches)
    fetches.append(
        image_fetcher.get_image_bytes(
            inspection_time=insp_time_str,
            wafer_key=wafer_key,
            defect_id=defect_id,
            image_type="PATCH_DEFECTIVE",
        )
    )
    difference_fetch_index = len(fetches)
    fetches.append(
        image_fetcher.get_image_bytes(
            inspection_time=insp_time_str,
            wafer_key=wafer_key,
            defect_id=defect_id,
            image_type="difference",
        )
    )

    fetched = await asyncio.gather(*fetches)

    for review_image, review_fetch_index in review_fetches:
        review_bytes = fetched[review_fetch_index]
        images.append(
            {
                "image_id": str(review_image.image_id),
                "image_type": review_image.image_type or "REVIEW_HIGH_MAG",
                "role": "review",
                "content_type": "image/png",
                "filename": review_image.image_name,
                "bytes": review_bytes,
                "source_uri": (
                    f"mock-sc://review/{insp_time_str}/{wafer_key}/{defect_id}/"
                    f"{review_image.image_id}"
                ),
            }
        )

    template_bytes = fetched[template_fetch_index]
    images.append(
        {
            "image_id": f"{defect_id}_template",
            "image_type": "PATCH_TEMPLATE",
            "role": "patch_template",
            "content_type": "image/png",
            "filename": "template.png",
            "bytes": template_bytes,
            "source_uri": (
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/template.png"
            ),
        }
    )

    defective_bytes = fetched[defective_fetch_index]
    images.append(
        {
            "image_id": f"{defect_id}_defective",
            "image_type": "PATCH_DEFECTIVE",
            "role": "patch_defective",
            "content_type": "image/png",
            "filename": "defective.png",
            "bytes": defective_bytes,
            "source_uri": (
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/defective.png"
            ),
        }
    )

    difference_bytes = fetched[difference_fetch_index]
    images.append(
        {
            "image_id": f"{defect_id}_difference",
            "image_type": "PATCH_DIFFERENCE",
            "role": "patch_difference",
            "content_type": "image/png",
            "filename": "difference.png",
            "bytes": difference_bytes,
            "source_uri": (
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/difference.png"
            ),
        }
    )

    return images


class ScImportPrefectClient(Protocol):
    async def resolve_deployment_id(self, deployment_name: str) -> str | None: ...

    async def create_flow_run_from_deployment(
        self,
        deployment_id: str,
        parameters: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]: ...


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
        prefect_client: ScImportPrefectClient,
        repository: ScImportRepository,
        payload_store: ScImportPayloadStore,
        upstream_reader: ScUpstreamReader,
        image_fetcher: ScImageFetcher,
    ) -> None:
        self._prefect = prefect_client
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
        force_prefect_flow: bool = False,
    ) -> tuple[ScImportStatus, str | None]:
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
                return (
                    ScImportStatus(
                        status="completed",
                        source_inspection_time=source_inspection_time,
                        source_wafer_key=source_wafer_key,
                        dataset_name=dataset_name,
                        storage_mode=storage_mode,
                        imported_count=0,
                    ),
                    None,
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
            return (
                await self._fail(
                    "Failed to create dataset",
                    source_inspection_time,
                    source_wafer_key,
                    dataset_name,
                    storage_mode,
                ),
                None,
            )

        if (
            not force_prefect_flow
            and max_rows is not None
            and 0 < max_rows <= DIRECT_IMPORT_MAX_ROWS
        ):
            try:
                result = await self._run_direct_import(
                    dataset_id=dataset.id,
                    org_id=org_id,
                    source_inspection_time=source_inspection_time,
                    source_wafer_key=source_wafer_key,
                    max_rows=max_rows,
                    logger=logger,
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
                return completed_status, None
            except Exception as e:
                logger.exception("Direct import failed, dataset=%s", dataset.id)
                return (
                    await self._fail(
                        f"Direct import failed: {e}",
                        source_inspection_time,
                        source_wafer_key,
                        dataset_name,
                        storage_mode,
                    ),
                    None,
                )

        prefect_offset = 0
        prefect_max_rows = max_rows
        hybrid_imported_count = 0

        if (
            not force_prefect_flow
            and storage_mode == "file_shard_sparse"
            and (max_rows is None or max_rows > DIRECT_IMPORT_MAX_ROWS)
        ):
            try:
                result = await self._run_direct_import(
                    dataset_id=dataset.id,
                    org_id=org_id,
                    source_inspection_time=source_inspection_time,
                    source_wafer_key=source_wafer_key,
                    max_rows=DIRECT_IMPORT_MAX_ROWS,
                    logger=logger,
                )
                imported_count_raw = result.get("imported_count", 0)
                hybrid_imported_count = (
                    int(imported_count_raw)
                    if isinstance(imported_count_raw, (int, float))
                    else 0
                )
            except Exception as e:
                logger.exception("Hybrid direct import failed, dataset=%s", dataset.id)
                return (
                    await self._fail(
                        f"Hybrid direct import failed: {e}",
                        source_inspection_time,
                        source_wafer_key,
                        dataset_name,
                        storage_mode,
                    ),
                    None,
                )

            if hybrid_imported_count < DIRECT_IMPORT_MAX_ROWS:
                completed_status = ScImportStatus(
                    status="completed",
                    dataset_id=dataset.id,
                    dataset_name=dataset_name,
                    source_inspection_time=source_inspection_time,
                    source_wafer_key=source_wafer_key,
                    storage_mode=storage_mode,
                    imported_count=hybrid_imported_count,
                )
                return completed_status, None

            prefect_offset = DIRECT_IMPORT_MAX_ROWS
            if max_rows is not None:
                prefect_max_rows = max_rows - DIRECT_IMPORT_MAX_ROWS

        try:
            deployment_id = await self._prefect.resolve_deployment_id(
                "sc-import-deployment"
            )
        except Exception as e:
            return (
                await self._fail(
                    f"Prefect API error: {e}",
                    source_inspection_time,
                    source_wafer_key,
                    dataset_name,
                    storage_mode,
                ),
                None,
            )

        if deployment_id is None:
            return (
                await self._fail(
                    "Deployment 'sc-import-deployment' not found",
                    source_inspection_time,
                    source_wafer_key,
                    dataset_name,
                    storage_mode,
                ),
                None,
            )

        try:
            run = await self._prefect.create_flow_run_from_deployment(
                deployment_id=deployment_id,
                parameters={
                    "source_inspection_time": source_inspection_time,
                    "source_wafer_key": source_wafer_key,
                    "dataset_name": dataset_name,
                    "storage_mode": storage_mode,
                    "filters": filters,
                    "label_space": label_space,
                    "dataset_id": dataset.id,
                    "org_id": org_id,
                    "max_rows": prefect_max_rows,
                    "offset": prefect_offset,
                },
            )
            flow_run_id = run["id"]
        except Exception as e:
            return (
                await self._fail(
                    f"Failed to submit flow run: {e}",
                    source_inspection_time,
                    source_wafer_key,
                    dataset_name,
                    storage_mode,
                ),
                None,
            )

        running_status = ScImportStatus(
            status="running",
            flow_run_id=flow_run_id,
            source_inspection_time=source_inspection_time,
            source_wafer_key=source_wafer_key,
            dataset_name=dataset_name,
            dataset_id=dataset.id,
            storage_mode=storage_mode,
            imported_count=hybrid_imported_count,
        )
        return running_status, flow_run_id

    async def _run_direct_import(
        self,
        *,
        dataset_id: str,
        org_id: str,
        source_inspection_time: str,
        source_wafer_key: int,
        max_rows: int | None = None,
        logger: logging.Logger | logging.LoggerAdapter | None = None,
    ) -> dict[str, object]:
        """Direct sparse import for small datasets (≤30k rows)."""
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
            payload_store=cast(DatasetPayloadStore, self._payload_store),
        )
        shard_entries: list[ShardEntry] = []
        sample_index: dict[str, SampleLocator] = {}
        total_rows = 0
        shard_count = 0
        batch_size = 1000

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
            await self._payload_store.put_manifest(manifest, org_id=org_id)

        batch: list[dict[str, Any]] = []
        async for chunk in self._upstream.stream(
            source_inspection_time, source_wafer_key
        ):
            for patch_sample in iter_patch_samples_from_upstream_chunk(chunk):
                images = await _build_image_structs(
                    patch_sample=patch_sample,
                    inspection_time=insp_dt,
                    wafer_key=source_wafer_key,
                    image_fetcher=self._image_fetcher,
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
                    batch = []

                if max_rows is not None and total_rows >= max_rows:
                    break

            if max_rows is not None and total_rows >= max_rows:
                break

        if batch and (max_rows is None or total_rows < max_rows):
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

        if shard_count == 0:
            await publish_manifest()

        if logger is not None:
            logger.info(
                "Sparse import complete: %d rows across %d shards",
                total_rows,
                shard_count,
            )

        return {"dataset_id": dataset_id, "imported_count": total_rows}

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
