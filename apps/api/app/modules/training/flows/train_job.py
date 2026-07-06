from __future__ import annotations
# pyright: reportMissingImports=false

import asyncio
import json
import os
import uuid
from typing import Any
from urllib.parse import quote

from prefect import flow, get_run_logger
from platform_runtime.contracts import DatasetRef, TrainContext, TrainResult
from app.shared.db.models.artifacts import ArtifactORM
from app.shared.db.models.datasets import DatasetORM


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
    runtime_metadata = metadata.copy() if isinstance(metadata, dict) else {}
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
        "label_space": label_space,
        "source_dataset_id": dataset_meta.get("id", "")
        if isinstance(dataset_meta, dict)
        else getattr(dataset_meta, "id", ""),
    }


async def run_training_pipeline(
    job_id: str,
    dataset_id: str,
    trainer_id: str,
    artifact_storage: Any | None = None,
    materialization_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.composition import AppContainer, build_flow_container
    from app.core.config import load_config
    from app.core.registry import get_dataset_model, get_trainer

    import app.registrations  # noqa: F401  # trigger all mapper registrations

    logger = get_run_logger()

    # Ensure SC trainer and all catalog-backed trainers are registered
    from app.modules.training.flows._trainers import sc  # noqa: F401
    from app.modules.training.flows._trainers import yolo_sc  # noqa: F401

    container: AppContainer | None = None
    should_close = True
    try:
        cfg = load_config(skip_runtime_validation=True)
        container = build_flow_container(cfg)
        should_close = True
    except Exception:
        logger.exception(
            "build_flow_container failed for job_id=%s dataset_id=%s",
            job_id,
            dataset_id,
        )
        raise

    if artifact_storage is None:
        artifact_storage = container.artifact_storage

    logger.info(
        "Training runner: job_id=%s dataset_id=%s trainer_id=%s",
        job_id,
        dataset_id,
        trainer_id,
    )

    async with container.session_factory() as session:
        dataset_row = await session.get(DatasetORM, dataset_id)
    if dataset_row is None:
        raise ValueError(f"Dataset not found: {dataset_id}")
    label_space: list[str] = list(
        getattr(dataset_row, "dataset_meta", {}).get("label_space", [])
        if isinstance(getattr(dataset_row, "dataset_meta", None), dict)
        else []
    )

    trainer_callable = get_trainer(trainer_id)
    if trainer_callable is None:
        raise ValueError(f"Trainer not found: {trainer_id}")
    model_cls = get_dataset_model(dataset_row.dataset_type)
    if model_cls is None:
        raise ValueError(
            f"No dataset model registered for dataset_type='{dataset_row.dataset_type}'"
        )
    from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
    from app.shared.db.sql_repository import SqlRepository

    factory = DatasetStorageFactory(
        repo=SqlRepository(session_factory=container.session_factory),
        storage=container.artifact_storage,
        payload_store=container.dataset_payload_store,
        ls_client=container.label_studio_client,
        session_factory=container.session_factory,
    )
    storage = await factory.open(dataset_id, org_id=dataset_row.org_id)
    lf = await storage.list_samples(with_labels=True, return_lazyframe=True)

    ctx = TrainContext(
        job_id=job_id,
        dataset_ref=DatasetRef(
            dataset_id=dataset_id,
            label_space=label_space,
        ),
    )

    logger.info("Calling trainer")
    image_fetcher = None
    if dataset_row.dataset_type == "image_sc":
        import os as _os_tj
        from app.modules.sc.adapter.grpc_image_fetcher import GrpcImageFetcher

        image_fetcher = GrpcImageFetcher(
            addr=_os_tj.environ.get("IMAGE_PARSER_GRPC_ADDR", "image-parser:9092")
        )
    result = trainer_callable(
        ctx,
        artifact_storage=artifact_storage,
        lazyframe=lf,
        image_fetcher=image_fetcher,
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
        "id": dataset_row.id,
        "dataset_meta": dataset_row.dataset_meta,
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
        async with container.session_factory() as session:
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

    if should_close:
        await container.close()

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
) -> dict[str, Any]:
    logger = get_run_logger()
    logger.info(
        "train-job flow started: job_id=%s dataset_id=%s trainer_id=%s created_by=%s",
        job_id,
        dataset_id,
        trainer_id,
        created_by,
    )

    mat_ref: dict[str, Any] | None = None
    if materialization_ref is not None:
        mat_ref = json.loads(materialization_ref)

    return await run_training_pipeline(
        job_id=job_id,
        dataset_id=dataset_id,
        trainer_id=trainer_id,
        materialization_ref=mat_ref,
    )
