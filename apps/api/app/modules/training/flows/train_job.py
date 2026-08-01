from __future__ import annotations
# pyright: reportMissingImports=false

import asyncio
import json
import logging
import os
import uuid
from contextlib import AsyncExitStack
from typing import Any, cast
from urllib.parse import quote

from prefect import flow, get_run_logger
from app.shared.domain.runtime import DatasetRef, TrainContext, TrainResult
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.context import AppContext
from app.shared.db.models.artifacts import ArtifactORM
from app.shared.db.models.datasets import DatasetORM

logger = logging.getLogger(__name__)


def _get_training_logger() -> logging.Logger | Any:
    try:
        return get_run_logger()
    except Exception:
        return logger


def _resolve_uri(uri: str) -> str:
    if not uri or "://" in uri or uri.startswith("data:"):
        return uri
    base = os.environ.get("PLATFORM_API_URL", "http://api:8000").rstrip("/")
    return f"{base}/api/v1/images/resolve?uri={quote(uri, safe='')}"


def build_trained_model_metadata(
    dataset_meta: dict[str, Any] | None,
    trainer_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.modules.types import catalog

    runtime_metadata = metadata.copy() if isinstance(metadata, dict) else {}
    trainer = catalog.get_trainer_meta(trainer_id)
    label_space = runtime_metadata.get("label_space")
    if not isinstance(label_space, list):
        label_space = []
    if dataset_meta and isinstance(dataset_meta, dict):
        ds_meta = (
            dataset_meta.get("dataset_meta") or dataset_meta.get("task_spec") or {}
        )
        if not label_space and isinstance(ds_meta, dict):
            label_space = list(ds_meta.get("label_space", []))
    elif not label_space and dataset_meta and hasattr(dataset_meta, "dataset_meta"):
        label_space = list(
            getattr(dataset_meta, "dataset_meta", {}).get("label_space", [])
        )
    return {
        **runtime_metadata,
        "trainer_id": trainer_id,
        "model_contract": trainer.output_model.contract,
        "model_schema_version": trainer.output_model.schema_version,
        "predictor_ids": list(trainer.predictor_ids),
        "label_space": label_space,
        "source_dataset_id": dataset_meta.get("id", "")
        if isinstance(dataset_meta, dict)
        else getattr(dataset_meta, "id", ""),
    }


async def run_training_pipeline(
    job_id: str,
    dataset_id: str,
    trainer_id: str,
    sample_ids: list[str] | None = None,
    sample_filter: dict[str, Any] | None = None,
    missing_image_policy: str | None = None,
    artifact_storage: Any | None = None,
    materialization_ref: dict[str, Any] | None = None,
    app_context: AppContext | None = None,
) -> dict[str, Any]:
    from app.composition import build_flow_app_context, close_flow_app_context
    from app.core.config import load_config

    owns_context = app_context is None
    if app_context is None:
        try:
            cfg = load_config(skip_runtime_validation=True)
            app_context = build_flow_app_context(cfg)
        except Exception:
            _get_training_logger().exception(
                "build_flow_app_context failed for job_id=%s dataset_id=%s",
                job_id,
                dataset_id,
            )
            raise
    try:
        return await _run_training_pipeline_with_context(
            app_context=app_context,
            job_id=job_id,
            dataset_id=dataset_id,
            trainer_id=trainer_id,
            sample_ids=sample_ids,
            sample_filter=sample_filter,
            missing_image_policy=missing_image_policy,
            artifact_storage=artifact_storage,
            materialization_ref=materialization_ref,
        )
    finally:
        if owns_context:
            await close_flow_app_context(app_context)


async def _run_training_pipeline_with_context(
    *,
    app_context: AppContext,
    job_id: str,
    dataset_id: str,
    trainer_id: str,
    sample_ids: list[str] | None,
    sample_filter: dict[str, Any] | None,
    missing_image_policy: str | None,
    artifact_storage: Any | None,
    materialization_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    from app.core.registry import resolve_view_types
    from app.modules.types import catalog
    from app.modules.runtime.app.services.executable_loader import get_trainer

    import app.registrations  # noqa: F401  # trigger all mapper registrations

    logger = _get_training_logger()

    if materialization_ref is not None:
        raise ValueError(
            "API-local compatibility training does not accept a pre-materialized "
            "reference; external runtimes must consume the data-plane manifest "
            "through their own deployment"
        )
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    storage_factory = app_context.injector.get(DatasetStorageFactoryPort)

    if artifact_storage is None:
        artifact_storage = app_context.shared.artifact_storage

    logger.info(
        "Training runner: job_id=%s dataset_id=%s trainer_id=%s",
        job_id,
        dataset_id,
        trainer_id,
    )

    async with app_context.shared.session_factory() as session:
        dataset_row = await session.get(DatasetORM, dataset_id)
        if dataset_row is None:
            raise ValueError(f"Dataset not found: {dataset_id}")
        dataset_type = dataset_row.dataset_type
        dataset_org_id = dataset_row.org_id
        dataset_storage_mode = str(dataset_row.storage_mode)
        dataset_meta_json = (
            dict(dataset_row.dataset_meta)
            if isinstance(dataset_row.dataset_meta, dict)
            else {}
        )
    label_space: list[str] = list(dataset_meta_json.get("label_space", []))

    trainer_callable = get_trainer(trainer_id)
    trainer_metadata = catalog.get_trainer_meta(trainer_id)
    dataset_view_types = resolve_view_types(dataset_type)
    if trainer_metadata.view_id not in dataset_view_types:
        raise ValueError(
            f"Trainer {trainer_id!r} requires view "
            f"{trainer_metadata.view_id!r}, dataset type {dataset_type!r} "
            f"provides {dataset_view_types}"
        )
    storage = await storage_factory.open(
        dataset_id,
        org_id=dataset_org_id,
    )
    lf = await storage.list_samples(
        with_labels=True,
        with_predictions=sample_filter is not None,
        return_lazyframe=True,
        sample_ids=sample_ids,
    )
    if sample_filter is not None:
        if dataset_type != "image_sc":
            raise ValueError("sample_filter is only supported for image_sc datasets")
        from app.modules.sc.app.services.sample_filter import (
            parse_and_apply_workflow_sample_filter,
        )

        lf = parse_and_apply_workflow_sample_filter(cast(Any, lf), sample_filter)
    if dataset_type == "image_sc":
        from app.modules.sc.app.services.training_selection import (
            limit_sc_training_rows_per_class,
        )

        lf = limit_sc_training_rows_per_class(lf)

    ctx = TrainContext(
        job_id=job_id,
        dataset_ref=DatasetRef(
            dataset_id=dataset_id,
            label_space=label_space,
        ),
    )

    materializers = catalog.capabilities.materializers_for(
        trainer_metadata.view_id,
        purpose="train",
        storage_mode=dataset_storage_mode,
    )
    if len(materializers) != 1:
        raise RuntimeError(
            f"Expected exactly one materializer for "
            f"view={trainer_metadata.view_id!r}, purpose='train', "
            f"storage_mode={dataset_storage_mode!r}; found "
            f"{[item.id for item in materializers]}"
        )
    from app.runtime_compat.materializers import resolve_local_materializer

    materializer_metadata = materializers[0]
    materializer = resolve_local_materializer(
        app_context.injector,
        materializer_metadata.id,
    )
    view_metadata = catalog.get_view_meta(trainer_metadata.view_id)

    logger.info("Materializing trainer input view")
    async with AsyncExitStack() as exit_stack:
        materialization = await materializer.materialize(
            rows_lazyframe=lf,
            dataset_id=dataset_id,
            job_id=job_id,
            image_types=list(view_metadata.image_roles),
        )
        exit_stack.callback(materialization.cleanup)
        if materialization.errors and missing_image_policy != "skip":
            raise ValueError(
                f"Materialization for trainer {trainer_id!r} failed for "
                f"{len(materialization.errors)} image(s); first error: "
                f"{materialization.errors[0]}"
            )

        logger.info("Calling trainer")
        result = trainer_callable(
            ctx,
            artifact_storage=artifact_storage,
            materialized_dataset=materialization.dataset,
            materialization_manifest=materialization.manifest,
            missing_image_policy=missing_image_policy,
        )
        if asyncio.iscoroutine(result):
            result = await result
    if isinstance(result, dict):
        train_result = TrainResult(
            model_uri=str(result.get("model_uri", "")),
            metrics=result.get("metrics", {})
            if isinstance(result.get("metrics", {}), dict)
            else {},
            artifact_uris=result.get("artifact_uris", [])
            if isinstance(result.get("artifact_uris", []), list)
            else [],
            metadata=result.get("metadata", {})
            if isinstance(result.get("metadata", {}), dict)
            else {},
        )
    elif isinstance(result, TrainResult):
        train_result = result
    else:
        raise TypeError("Trainer must return TrainResult or dict")

    dataset_meta = {
        "id": dataset_id,
        "dataset_meta": dataset_meta_json,
    }

    artifacts: list[dict[str, Any]] = [
        {
            "uri": train_result.model_uri,
            "kind": "model",
            "metadata": build_trained_model_metadata(
                dataset_meta, trainer_id, train_result.metadata
            ),
        },
    ]
    for uri in train_result.artifact_uris:
        if uri and uri != train_result.model_uri:
            artifacts.append({"uri": uri, "kind": "metrics", "metadata": {}})

    if artifacts:
        async with app_context.shared.session_factory() as session:
            for a in artifacts:
                session.add(
                    ArtifactORM(
                        id=str(uuid.uuid4()),
                        job_id=job_id,
                        uri=a["uri"],
                        kind=str(a.get("kind", "artifact")),
                        metadata_json=a["metadata"]
                        if isinstance(a.get("metadata"), dict)
                        else {},
                    )
                )
            await session.commit()

    return {
        "job_id": job_id,
        "status": "completed",
        "artifacts": [a for a in artifacts if a.get("uri")],
        "metrics": train_result.metrics,
    }


@flow(name="training-train-job")
async def train_job_flow(
    job_id: str,
    dataset_id: str,
    trainer_id: str,
    created_by: str = "system",
    materialization_ref: str | None = None,
    catalog_id: str | None = None,
    input_contract: str | None = None,
    output_contract: str | None = None,
    resource_profile: str | None = None,
    owner: str | None = None,
    algo_id: str | None = None,
    algo_version: str | None = None,
    code_version: str | None = None,
    missing_image_policy: str | None = None,
) -> dict[str, Any]:
    from app.modules.types import catalog

    logger = get_run_logger()
    logger.info(
        "train-job flow started: job_id=%s dataset_id=%s trainer_id=%s created_by=%s",
        job_id,
        dataset_id,
        trainer_id,
        created_by,
    )
    if catalog_id is None or catalog_id != trainer_id:
        raise ValueError("Training flow requires catalog_id matching trainer_id")
    if owner != "local_compat":
        raise ValueError("API-local training flow requires owner='local_compat'")
    trainer_metadata = catalog.get_trainer_meta(trainer_id)
    if input_contract != trainer_metadata.input_view.contract:
        raise ValueError(
            f"Training route input_contract={input_contract!r} does not match "
            f"trainer view contract={trainer_metadata.input_view.contract!r}"
        )
    if output_contract != trainer_metadata.output_model.contract:
        raise ValueError(
            f"Training route output_contract={output_contract!r} does not match "
            f"trainer model contract={trainer_metadata.output_model.contract!r}"
        )
    if missing_image_policy not in {"fail", "skip"}:
        raise ValueError(
            "Training route missing_image_policy must be explicitly 'fail' or 'skip'"
        )
    logger.info(
        "Training runtime route: catalog=%s input=%s output=%s profile=%s "
        "algo=%s@%s code=%s missing_image_policy=%s",
        catalog_id,
        input_contract,
        output_contract,
        resource_profile,
        algo_id,
        algo_version,
        code_version,
        missing_image_policy,
    )

    mat_ref: dict[str, Any] | None = None
    if materialization_ref is not None:
        mat_ref = json.loads(materialization_ref)

    return await run_training_pipeline(
        job_id=job_id,
        dataset_id=dataset_id,
        trainer_id=trainer_id,
        materialization_ref=mat_ref,
        missing_image_policy=missing_image_policy,
    )
