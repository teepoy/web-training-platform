from __future__ import annotations

import argparse
import asyncio
import json
from typing import TYPE_CHECKING, Any

from app.core.config import load_config
from app.shared.db.session import create_engine, create_session_factory
from app.domain.models import ArtifactRef
from app.modules.presets._registry import get_preset, get_preset_meta
from app.modules.presets.registry import PresetRegistry
from app.shared.domain.runtime import DatasetRef, ModelRef, TrainContext, TrainResult
from app.shared.db.sql_repository import SqlRepository
from app.shared.application.compatibility import (
    build_trained_model_metadata,
    validate_dataset_preset_training,
)
from app.shared.infrastructure.workers.embedding import EmbeddingClient
from app.shared.infrastructure.llm.client import OpenAICompatibleLlmClient
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage
from app.shared.infrastructure.storage.minio import MinioArtifactStorage

if TYPE_CHECKING:
    pass


def _build_storage() -> Any:
    cfg = load_config()
    if str(cfg.storage.kind) == "minio":
        return MinioArtifactStorage(
            endpoint=str(cfg.storage.minio.endpoint),
            access_key=str(cfg.storage.minio.access_key),
            secret_key=str(cfg.storage.minio.secret_key),
            bucket=str(cfg.storage.minio.bucket),
            secure=bool(cfg.storage.minio.secure),
        )
    return InMemoryArtifactStorage()


def _build_embedding_client() -> EmbeddingClient:
    cfg = load_config()
    return EmbeddingClient(grpc_target=str(cfg.embedding.grpc_target))


def _build_llm_client() -> OpenAICompatibleLlmClient:
    cfg = load_config()
    return OpenAICompatibleLlmClient(
        base_url=str(cfg.llm.base_url),
        api_key=str(cfg.llm.api_key),
        model=str(cfg.llm.model),
        timeout_seconds=float(cfg.llm.timeout_seconds),
    )


async def _invoke_trainer(
    trainer: Any,
    ctx: TrainContext,
) -> TrainResult:
    """Invoke trainer.train(ctx) and normalize the result to TrainResult."""
    import inspect

    result = trainer.train(ctx)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, TrainResult):
        return result
    if isinstance(result, dict):
        return TrainResult(
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
    raise TypeError("Trainer.train must return TrainResult or dict")


async def _load_dataset_records(
    repo: SqlRepository, dataset_id: str
) -> tuple[list[dict[str, Any]], list[str]]:
    dataset = await repo.get_dataset(dataset_id)
    label_space = list(dataset.task_spec.label_space) if dataset is not None else []
    annotations = await repo.list_annotations_for_dataset(dataset_id)
    latest_labels: dict[str, str] = {}
    for ann in sorted(annotations, key=lambda x: x.created_at):
        latest_labels[ann.sample_id] = ann.label

    offset = 0
    limit = 200
    records: list[dict[str, Any]] = []
    while True:
        samples, total = await repo.list_samples(dataset_id, offset=offset, limit=limit)
        for sample in samples:
            question = ""
            answer = None
            if isinstance(sample.metadata, dict):
                question = str(sample.metadata.get("question", ""))
                if sample.metadata.get("answer") is not None:
                    answer = str(sample.metadata.get("answer"))
            image_uri = sample.image_uris[0] if sample.image_uris else ""
            records.append(
                {
                    "sample_id": sample.id,
                    "image_uri": image_uri,
                    "question": question,
                    "answer": answer,
                    "label": latest_labels.get(sample.id, ""),
                }
            )
        offset += limit
        if offset >= total:
            break
    return records, label_space


async def run_training_pipeline(
    job_id: str,
    dataset_id: str,
    preset_id: str,
    artifact_storage: Any | None = None,
    embedding_client: EmbeddingClient | None = None,
    llm_client: OpenAICompatibleLlmClient | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    engine = create_engine(str(cfg.db.url), echo=bool(cfg.db.echo))
    session_factory = create_session_factory(engine)
    repo = SqlRepository(session_factory=session_factory)
    dataset = await repo.get_dataset(dataset_id)
    if dataset is None:
        await engine.dispose()
        raise ValueError(f"Dataset not found: {dataset_id}")
    records, label_space = await _load_dataset_records(repo, dataset_id)

    # ---- new: decorator-based registry (no YAML, no string imports) ----
    preset_cls = get_preset(preset_id)
    if preset_cls is None:
        await engine.dispose()
        raise ValueError(f"Preset not found: {preset_id}")

    meta = get_preset_meta(preset_id)
    if meta is None or not meta.trainable:
        await engine.dispose()
        raise ValueError(f"Preset is not trainable: {preset_id}")

    # Build PresetSpec for trainer compat (trainers read ctx.preset.*)
    preset_spec = PresetRegistry._decorator_meta_to_spec(meta)

    validate_dataset_preset_training(dataset, preset_spec)

    # ---- pipeline: load & transform records via preset ----
    if hasattr(preset_cls, "pipeline"):
        pipeline = preset_cls.pipeline()
        if pipeline is not None and hasattr(pipeline, "load"):
            dataset_ref = DatasetRef(
                dataset_id=dataset_id,
                label_space=label_space,
                metadata={"records": records},
            )
            loaded = await pipeline.load(dataset_ref)
            if isinstance(loaded, list):
                records = loaded

    # ---- trainer: instantiated via preset, not string import ----
    trainer = preset_cls.train(
        artifact_storage=artifact_storage or _build_storage(),
        llm_client=llm_client or _build_llm_client(),
        embedding_client=embedding_client or _build_embedding_client(),
        config=meta,  # pass full meta for typed config access
    )
    if trainer is None:
        await engine.dispose()
        raise ValueError(f"Preset.train() returned None for preset: {preset_id}")

    ctx = TrainContext(
        job_id=job_id,
        preset=preset_spec,
        model_ref=ModelRef(
            framework=meta.model.get("framework", "pytorch"),
            architecture=meta.model.get("architecture", ""),
            base_model=meta.model.get("base_model", ""),
            checkpoint=meta.model.get("checkpoint"),
            num_classes=meta.model.get("num_classes"),
        ),
        dataset_ref=DatasetRef(
            dataset_id=dataset_id,
            label_space=label_space,
            metadata={"records": records},
        ),
    )

    train_result = await _invoke_trainer(trainer, ctx)
    await engine.dispose()
    artifacts = [
        {
            "uri": train_result.model_uri,
            "kind": "model",
            "metadata": build_trained_model_metadata(
                dataset, preset_spec, train_result.metadata
            ),
        },
    ]
    for uri in train_result.artifact_uris:
        if uri and uri != train_result.model_uri:
            artifacts.append({"uri": uri, "kind": "metrics", "metadata": {}})
    artifact_refs = [
        ArtifactRef(
            uri=str(item["uri"]),
            kind=str(item.get("kind", "artifact")),
            metadata=item["metadata"] if isinstance(item.get("metadata"), dict) else {},  # type: ignore
        )
        for item in artifacts
        if isinstance(item, dict) and item.get("uri")
    ]
    if artifact_refs:
        await repo.add_artifacts(job_id, artifact_refs)
    return {
        "job_id": job_id,
        "status": "completed",
        "artifacts": [a for a in artifacts if a.get("uri")],
        "metrics": train_result.metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run training pipeline")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--preset-id", required=True)
    args = parser.parse_args()
    result = asyncio.run(
        run_training_pipeline(
            job_id=args.job_id,
            dataset_id=args.dataset_id,
            preset_id=args.preset_id,
        )
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
