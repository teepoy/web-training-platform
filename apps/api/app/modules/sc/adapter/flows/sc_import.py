from __future__ import annotations
# pyright: reportMissingImports=false

import asyncio
from datetime import datetime, timezone
from typing import Any

from prefect import flow, get_run_logger

from app.modules.sc.app.services.import_rows import (
    _geometry_from_inspection,
    iter_patch_samples_from_upstream_chunk,
)
from app.modules.sc.app.services.shuffle import get_shuffled_ids
from app.modules.sc.schema import SC_SPARSE_SHARD_SCHEMA_V2
from app.shared.api.schemas import (
    Dataset,
    DatasetStorageMode,
    SPARSE_NO_LS,
    TaskSpec,
)


async def _with_flow_app_context() -> tuple[Any, bool]:
    from app.composition import build_flow_app_context
    from app.core.config import load_config

    cfg = load_config()
    return build_flow_app_context(cfg), True


def _make_label_config(label_space: list[str] | None) -> str:
    from app.shared.infrastructure.label_studio.client import (
        LabelStudioClient,
    )

    return LabelStudioClient.generate_image_classification_config(label_space or [])


# ── SC domain helpers ───────────────────────────────────────────────────────


async def _build_image_structs(
    *,
    patch_sample: Any,
    inspection_time: Any,
    wafer_key: int,
    image_fetcher: Any,
) -> list[Any]:
    """Fetch all images for a single SC defect, returning BulkImageRef objects.

    Fetches review images, PATCH_TEMPLATE, PATCH_DEFECTIVE, and difference
    images in parallel via ``asyncio.gather``.
    """
    from app.modules.datasets.domain.sample_row import BulkImageRef

    images: list[Any] = []
    defect_id = patch_sample.defect_id
    insp_time_str = (
        inspection_time.isoformat()
        if hasattr(inspection_time, "isoformat")
        else str(inspection_time)
    )

    review_images: list[Any] = getattr(patch_sample, "review_images", []) or []
    review_fetches: list[tuple[Any, int]] = []

    fetches: list[Any] = []
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
            BulkImageRef(
                image_id=str(review_image.image_id),
                image_type=review_image.image_type or "REVIEW_HIGH_MAG",
                role="review",
                content_type="image/png",
                filename=review_image.image_name,
                bytes_=review_bytes,
                source_uri=(
                    f"mock-sc://review/{insp_time_str}/{wafer_key}/{defect_id}/"
                    f"{review_image.image_id}"
                ),
            )
        )

    template_bytes = fetched[template_fetch_index]
    images.append(
        BulkImageRef(
            image_id=f"{defect_id}_template",
            image_type="PATCH_TEMPLATE",
            role="patch_template",
            content_type="image/png",
            filename="template.png",
            bytes_=template_bytes,
            source_uri=(
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/template.png"
            ),
        )
    )

    defective_bytes = fetched[defective_fetch_index]
    images.append(
        BulkImageRef(
            image_id=f"{defect_id}_defective",
            image_type="PATCH_DEFECTIVE",
            role="patch_defective",
            content_type="image/png",
            filename="defective.png",
            bytes_=defective_bytes,
            source_uri=(
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/defective.png"
            ),
        )
    )

    difference_bytes = fetched[difference_fetch_index]
    images.append(
        BulkImageRef(
            image_id=f"{defect_id}_difference",
            image_type="PATCH_DIFFERENCE",
            role="patch_difference",
            content_type="image/png",
            filename="difference.png",
            bytes_=difference_bytes,
            source_uri=(
                f"mock-sc://patch/{insp_time_str}/{wafer_key}/{defect_id}/difference.png"
            ),
        )
    )

    return images


def _patch_sample_to_parquet_row(ps: Any, images: list[Any]) -> Any:
    """Convert a PatchSample + fetched images into a BulkSampleRow.

    SC-specific fields (defect_id, wafer_key, etc.) are placed in the
    ``extra`` dict so they become additional shard columns.
    """
    from app.modules.datasets.domain.sample_row import BulkSampleRow

    inspection_time_str = ""
    if ps.inspection_time is not None:
        inspection_time_str = ps.inspection_time.isoformat()

    return BulkSampleRow(
        sample_id=ps.sample_id,
        images=images,
        extra={
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
        },
    )


@flow(name="sc-import-upstream")
async def sc_import(
    source_inspection_time: str,
    source_wafer_key: int,
    dataset_name: str,
    storage_mode: str = "file_shard_sparse",
    filters: dict | None = None,
    label_space: list[str] | None = None,
    dataset_id: str | None = None,
    org_id: str | None = None,
    max_rows: int | None = None,
    offset: int = 0,
    total_available: int | None = None,
) -> dict:
    import app.registrations  # noqa: F401  # trigger all mapper registrations

    logger = get_run_logger()
    logger.info(
        "Starting sc-import: inspection_time=%s wafer_key=%s dataset=%s",
        source_inspection_time,
        source_wafer_key,
        dataset_name,
    )

    ctx, should_close = await _with_flow_app_context()
    try:
        repo = ctx.sc.repository
        ls_client = ctx.shared.label_studio_client
        upstream = ctx.sc.upstream_reader

        if dataset_id is None:
            # Pre-check upstream for data before creating dataset
            try:
                insp_dt = datetime.fromisoformat(source_inspection_time)
                lf = await upstream.list_samples(
                    insp_dt, source_wafer_key, offset=0, count=1
                )
                df = await lf.collect_async()
                if len(df) == 0:
                    logger.info(
                        "SC import: upstream has no data for inspection_time=%s "
                        "wafer_key=%d — skipping dataset creation",
                        source_inspection_time,
                        source_wafer_key,
                    )
                    return {"dataset_id": None, "imported_count": 0}
            except Exception:
                logger.warning(
                    "SC import: upstream pre-check failed — proceeding with dataset creation",
                    exc_info=True,
                )

        if dataset_id is None:
            if storage_mode == "file_shard_sparse":
                ls_project_id = SPARSE_NO_LS
            else:
                label_config = _make_label_config(label_space)
                project = await ls_client.create_project(dataset_name, label_config)
                ls_project_id = str(project.get("id", ""))
                logger.info("Created LS project: %s", ls_project_id)

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
                ls_project_id=ls_project_id,
                storage_mode=DatasetStorageMode(storage_mode),
            )
            dataset = await repo.create_dataset(dataset, org_id=org_id)
            dataset_id = dataset.id
            logger.info("Created dataset: %s", dataset_id)

            insp_dt_geo = datetime.fromisoformat(source_inspection_time)
            if insp_dt_geo.tzinfo is None:
                insp_dt_geo = insp_dt_geo.replace(tzinfo=timezone.utc)
            inspection = await upstream.get_inspection(insp_dt_geo, source_wafer_key)
            if inspection is not None:
                geometry = _geometry_from_inspection(inspection)
                await repo.update_dataset_meta(dataset_id, {"geometry": geometry})
        else:
            logger.info("Using pre-created dataset: %s", dataset_id)

        if dataset_id is None:
            raise RuntimeError("SC import dataset_id was not resolved")

        image_fetcher = ctx.sc.image_fetcher

        if storage_mode == "file_shard_sparse":
            from platform_runtime.sparse.models import ColumnSchema

            sc_columns = [
                ColumnSchema(name=c["name"], type=c["type"])
                for c in SC_SPARSE_SHARD_SCHEMA_V2
                if c["name"] not in ("sample_id", "images")
            ]

            storage = await ctx.datasets.dataset_storage_factory.open(
                dataset_id, org_id
            )

            insp_dt = datetime.fromisoformat(source_inspection_time)
            if insp_dt.tzinfo is None:
                insp_dt = insp_dt.replace(tzinfo=timezone.utc)

            lf = await upstream.list_samples(insp_dt, source_wafer_key, count=None)
            df = await lf.collect_async()
            total_rows_available = len(df)

            if total_rows_available == 0:
                return {"dataset_id": dataset_id, "imported_count": 0}

            indices = get_shuffled_ids(list(range(total_rows_available)))
            worker_indices = indices[offset:]
            if max_rows is not None:
                worker_indices = worker_indices[:max_rows]

            filtered_df = df[worker_indices]

            async def _iter_rows():
                imported = 0
                for patch_sample in iter_patch_samples_from_upstream_chunk(filtered_df):
                    if max_rows is not None and imported >= max_rows:
                        return
                    images = await _build_image_structs(
                        patch_sample=patch_sample,
                        inspection_time=insp_dt,
                        wafer_key=source_wafer_key,
                        image_fetcher=image_fetcher,
                    )
                    imported += 1
                    yield _patch_sample_to_parquet_row(patch_sample, images)

            imported_count = await storage.write_samples(
                _iter_rows(),
                schema_columns=sc_columns,
                batch_size=1000,
            )

            result = {"dataset_id": dataset_id, "imported_count": imported_count}
            logger.info("SC sparse import complete: %s", result)
            return result

        # ── db_full path ──────────────────────────────────────────────
        insp_dt = datetime.fromisoformat(source_inspection_time)
        if insp_dt.tzinfo is None:
            insp_dt = insp_dt.replace(tzinfo=timezone.utc)

        storage = await ctx.datasets.dataset_storage_factory.open(dataset_id, org_id)

        lf_db = await upstream.list_samples(insp_dt, source_wafer_key, count=None)
        df_db = await lf_db.collect_async()
        total_rows_available_db = len(df_db)

        if total_rows_available_db == 0:
            return {"dataset_id": dataset_id, "imported_count": 0}

        indices_db = get_shuffled_ids(list(range(total_rows_available_db)))
        worker_indices_db = indices_db[offset:]
        if max_rows is not None:
            worker_indices_db = worker_indices_db[:max_rows]

        filtered_df_db = df_db[worker_indices_db]

        async def _iter_rows():
            imported = 0
            for patch_sample in iter_patch_samples_from_upstream_chunk(filtered_df_db):
                if max_rows is not None and imported >= max_rows:
                    return
                images = await _build_image_structs(
                    patch_sample=patch_sample,
                    inspection_time=insp_dt,
                    wafer_key=source_wafer_key,
                    image_fetcher=image_fetcher,
                )
                row = _patch_sample_to_parquet_row(patch_sample, images)
                row.image_uris = [
                    img.source_uri or f"sc://{img.image_id}" for img in (images or [])
                ]
                imported += 1
                yield row

        imported_count = await storage.write_samples(
            _iter_rows(),
            batch_size=1000,
        )

        result = {"dataset_id": dataset_id, "imported_count": imported_count}
        logger.info("SC db_full import complete: %s", result)
        return result
    finally:
        if should_close:
            from app.composition import close_flow_app_context

            await close_flow_app_context(ctx)
