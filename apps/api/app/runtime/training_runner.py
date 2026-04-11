from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import os
from pathlib import Path
from typing import Any

from app.core.config import load_config
from app.db.session import create_engine, create_session_factory
from app.domain.models import ArtifactRef
from app.presets.registry import PresetRegistry
from app.presets.runtime import DatasetRef, ModelRef, TrainContext, TrainResult
from app.repositories.sql_repository import SqlRepository
from app.services.compatibility import build_trained_model_metadata, validate_dataset_preset_training
from app.services.embedding import EmbeddingClient
from app.services.llm import OpenAICompatibleLlmClient
from app.storage.minio_storage import InMemoryArtifactStorage, MinioArtifactStorage

_DEFAULT_PRESETS_DIR = str(Path(__file__).resolve().parents[2] / "presets")


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


def _load_callable(ref: str) -> Any:
    module_name, sep, attr_name = ref.partition(":")
    if sep != ":" or not module_name or not attr_name:
        raise ValueError(f"Invalid entrypoint reference: {ref}")
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


async def _invoke_entrypoint(
    fn: Any,
    ctx: TrainContext,
    artifact_storage: Any | None = None,
    embedding_client: EmbeddingClient | None = None,
    llm_client: OpenAICompatibleLlmClient | None = None,
) -> TrainResult:
    if inspect.isclass(fn):
        ctor_kwargs = {
            "artifact_storage": artifact_storage or _build_storage(),
            "embedding_client": embedding_client or _build_embedding_client(),
            "llm_client": llm_client or _build_llm_client(),
        }
        init_sig = inspect.signature(fn)
        params = init_sig.parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            trainer = fn(**ctor_kwargs)
        else:
            accepted = {k: v for k, v in ctor_kwargs.items() if k in params}
            trainer = fn(**accepted)
        if hasattr(trainer, "train"):
            result = trainer.train(ctx)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, TrainResult):
                return result
            if isinstance(result, dict):
                return TrainResult(
                    model_uri=str(result.get("model_uri", "")),
                    metrics=result.get("metrics", {}) if isinstance(result.get("metrics", {}), dict) else {},
                    artifact_uris=result.get("artifact_uris", []) if isinstance(result.get("artifact_uris", []), list) else [],
                    metadata=result.get("metadata", {}) if isinstance(result.get("metadata", {}), dict) else {},
                )
            raise TypeError("Trainer.train must return TrainResult or dict")
        raise TypeError("Trainer class entrypoint must expose train(ctx)")

    if hasattr(fn, "fn"):
        fn = fn.fn

    train_method = getattr(fn, "train", None)
    if callable(train_method):
        result = train_method(ctx)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, TrainResult):
            return result
        if isinstance(result, dict):
            return TrainResult(
                model_uri=str(result.get("model_uri", "")),
                metrics=result.get("metrics", {}) if isinstance(result.get("metrics", {}), dict) else {},
                artifact_uris=result.get("artifact_uris", []) if isinstance(result.get("artifact_uris", []), list) else [],
                metadata=result.get("metadata", {}) if isinstance(result.get("metadata", {}), dict) else {},
            )
        raise TypeError("Trainer.train must return TrainResult or dict")

    result = fn(ctx)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, TrainResult):
        return result
    if isinstance(result, dict):
        return TrainResult(
            model_uri=str(result.get("model_uri", "")),
            metrics=result.get("metrics", {}) if isinstance(result.get("metrics", {}), dict) else {},
            artifact_uris=result.get("artifact_uris", []) if isinstance(result.get("artifact_uris", []), list) else [],
            metadata=result.get("metadata", {}) if isinstance(result.get("metadata", {}), dict) else {},
        )
    raise TypeError("Training entrypoint must return TrainResult or dict")


async def _load_dataset_records(repo: SqlRepository, dataset_id: str) -> tuple[list[dict[str, Any]], list[str]]:
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

    presets_dir = os.environ.get("PRESETS_DIR", _DEFAULT_PRESETS_DIR)
    root = Path(presets_dir)
    if not root.is_absolute():
        root = (Path(__file__).resolve().parents[2] / presets_dir).resolve()
    registry = PresetRegistry(str(root), strict=True)
    registry.load()
    preset = registry.get_preset(preset_id)
    if preset is None:
        await engine.dispose()
        raise ValueError(f"Preset not found: {preset_id}")
    validate_dataset_preset_training(dataset, preset)

    entrypoint_ref = preset.train.entrypoint
    fn = _load_callable(entrypoint_ref)
    ctx = TrainContext(
        job_id=job_id,
        preset=preset,
        model_ref=ModelRef(
            framework=preset.model.framework,
            architecture=preset.model.architecture,
            base_model=preset.model.base_model,
            checkpoint=preset.model.checkpoint,
            num_classes=preset.model.num_classes,
        ),
        dataset_ref=DatasetRef(
            dataset_id=dataset_id,
            label_space=label_space,
            metadata={"records": records},
        ),
    )
    if preset.io.adapter:
        adapter_fn = _load_callable(preset.io.adapter)
        adapter = adapter_fn() if inspect.isclass(adapter_fn) else adapter_fn
        loaded = await adapter.load(ctx.dataset_ref)
        if isinstance(loaded, list):
            ctx.dataset_ref.metadata["records"] = loaded

    train_result = await _invoke_entrypoint(
        fn,
        ctx,
        artifact_storage=artifact_storage,
        embedding_client=embedding_client,
        llm_client=llm_client,
    )
    await engine.dispose()
    artifacts = [
        {
            "uri": train_result.model_uri,
            "kind": "model",
            "metadata": build_trained_model_metadata(dataset, preset, train_result.metadata),
        },
    ]
    for uri in train_result.artifact_uris:
        if uri and uri != train_result.model_uri:
            artifacts.append({"uri": uri, "kind": "metrics", "metadata": {}})
    artifact_refs = [
        ArtifactRef(
            uri=str(item["uri"]),
            kind=str(item.get("kind", "artifact")),
            metadata=item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {},
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
