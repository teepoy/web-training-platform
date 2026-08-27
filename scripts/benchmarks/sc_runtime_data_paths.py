from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from app.composition import build_flow_app_context, close_flow_app_context
from app.core.config import load_config
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.runtime.domain.context import (
    PredictionRuntimeContext,
    TrainingRuntimeContext,
)
from app.modules.runtime.domain.events import (
    ArtifactOutput,
    ArtifactOutputSink,
    LocalArtifactFile,
    StoredArtifact,
    collect_runtime_events,
)
from app.modules.sc.materialization.port.local import ScInspectionMaterializerPort
from app.modules.sc.runtime import ultralytics as runtime_ultralytics
from .sc_runtime_kernels import (
    fake_predict_yolo_stream,
    fake_train_yolo,
)
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.training.domain.repository import TrainingRepository
from app.shared.api.schemas import (
    Annotation,
    ArtifactRef,
    JobStatus,
    Model,
    PredictionEvent,
    PredictionJob,
    TrainingEvent,
)
from app.shared.context import AppContext

_TRAINER_ID = "yolo-sc-v1"
_PREDICTOR_ID = "yolo-sc-v1"


@dataclass(slots=True)
class _MaterializationMeasurement:
    elapsed_seconds: float = 0.0
    rows: int = 0
    bytes: int = 0
    errors: int = 0


class _MeasuredMaterializer:
    def __init__(self, delegate: ScInspectionMaterializerPort) -> None:
        self._delegate = delegate
        self.measurement = _MaterializationMeasurement()

    async def materialize(self, **kwargs: Any) -> Any:
        started = time.perf_counter()
        result = await self._delegate.materialize(**kwargs)
        elapsed = time.perf_counter() - started
        self.measurement = _MaterializationMeasurement(
            elapsed_seconds=elapsed,
            rows=result.row_count,
            bytes=sum(int(shard.size_bytes or 0) for shard in result.manifest.shards),
            errors=len(result.errors),
        )
        return result


class _BenchmarkTrainingRepository:
    def __init__(self) -> None:
        self.events: list[TrainingEvent] = []

    async def add_event(self, event: TrainingEvent) -> None:
        self.events.append(event)


class _BenchmarkPredictionRepository:
    def __init__(self, job: PredictionJob) -> None:
        self.job = job
        self.events: list[PredictionEvent] = []

    async def get_prediction_job(
        self,
        job_id: str,
        org_id: str | None = None,
    ) -> PredictionJob | None:
        if job_id != self.job.id or (org_id is not None and org_id != self.job.org_id):
            return None
        return self.job

    async def update_prediction_job_status(
        self,
        job_id: str,
        status: JobStatus,
        summary: dict | None = None,
    ) -> None:
        if job_id != self.job.id:
            raise LookupError(job_id)
        self.job = self.job.model_copy(
            update={
                "status": status,
                "summary": dict(summary or self.job.summary),
                "updated_at": datetime.now(UTC),
            }
        )

    async def add_prediction_event(self, event: PredictionEvent) -> None:
        self.events.append(event)


class _BenchmarkInjector:
    def __init__(
        self,
        delegate: Any,
        *,
        training_repository: _BenchmarkTrainingRepository,
        prediction_repository: _BenchmarkPredictionRepository,
        materializer: _MeasuredMaterializer,
    ) -> None:
        self._delegate = delegate
        self._bindings: dict[object, object] = {
            TrainingRepository: training_repository,
            PredictionRepository: prediction_repository,
            ScInspectionMaterializerPort: materializer,
        }

    def get(self, interface: object) -> object:
        binding = self._bindings.get(interface)
        return binding if binding is not None else self._delegate.get(interface)


class _BenchmarkArtifactSink(ArtifactOutputSink):
    def __init__(self, app_context: AppContext, run_id: str) -> None:
        self._storage = app_context.shared.artifact_storage
        self._run_id = run_id
        self.artifact: ArtifactRef | None = None

    async def persist(self, output: ArtifactOutput) -> ArtifactRef:
        match output.payload:
            case LocalArtifactFile(path=path, content_type=content_type):
                uri = await self._storage.put_file(
                    f"benchmarks/sc-runtime/{self._run_id}/{output.name or path.name}",
                    str(path),
                    content_type,
                )
                file_size = path.stat().st_size
            case StoredArtifact(uri=uri):
                file_size = None
            case _:
                raise AssertionError("unsupported benchmark artifact payload")
        artifact = ArtifactRef(
            id=output.id,
            uri=uri,
            kind=output.kind,
            metadata=dict(output.metadata),
            name=output.name,
            file_size=file_size,
            format=output.format,
            created_at=datetime.now(UTC),
        )
        self.artifact = artifact
        return artifact


async def _find_source_dataset(
    app_context: AppContext,
    *,
    dataset_id: str | None,
    dataset_name: str | None,
) -> Any:
    if app_context.datasets is None:
        raise RuntimeError("Dataset module is not initialized")
    repository = app_context.datasets.dataset_repository
    if dataset_id is not None:
        dataset = await repository.get_dataset(dataset_id)
        if dataset is None:
            raise LookupError(f"Dataset not found: {dataset_id}")
        return dataset
    assert dataset_name is not None
    matches = [
        dataset
        for dataset in await repository.list_datasets(
            query=dataset_name,
            limit=50,
        )
        if dataset.name == dataset_name
    ]
    if len(matches) != 1:
        raise LookupError(
            f"Expected one Dataset named {dataset_name!r}, found {len(matches)}"
        )
    return matches[0]


def _source_identity(dataset: Any) -> tuple[str, int]:
    metadata = dataset.dataset_meta if isinstance(dataset.dataset_meta, dict) else {}
    inspection_time = str(metadata.get("source_inspection_time") or "").strip()
    wafer_key_raw = metadata.get("source_wafer_key")
    if not inspection_time or wafer_key_raw is None:
        raise ValueError(
            "Source Dataset must include source_inspection_time and source_wafer_key"
        )
    return inspection_time, int(wafer_key_raw)


async def _create_benchmark_dataset(
    app_context: AppContext,
    *,
    source_dataset: Any,
    requested_samples: int,
    run_id: str,
) -> tuple[str, int]:
    if app_context.sc is None:
        raise RuntimeError("SC module is not initialized")
    org_id = str(source_dataset.org_id or "")
    if not org_id:
        raise ValueError("Source Dataset has no organization")
    inspection_time, wafer_key = _source_identity(source_dataset)
    labels = [str(label) for label in source_dataset.task_spec.label_space]
    if len(labels) < 2:
        raise ValueError("Source Dataset must declare at least two labels")
    status = await app_context.sc.sc_import_service.submit_upstream_import(
        source_inspection_time=inspection_time,
        source_wafer_key=wafer_key,
        dataset_name=f"SC runtime data-path benchmark {run_id}",
        org_id=org_id,
        created_by=str(source_dataset.created_by or "benchmark"),
        label_space=labels,
        max_rows=requested_samples,
    )
    if status.status != "completed" or not status.dataset_id:
        raise RuntimeError(f"Benchmark Dataset import failed: {status.error or status}")
    if status.imported_count != requested_samples:
        raise RuntimeError(
            "Benchmark Dataset import did not return the requested sample count: "
            f"requested={requested_samples} imported={status.imported_count}. "
            "Use an upstream fixture with at least the requested number of rows."
        )
    return status.dataset_id, status.imported_count


async def _label_benchmark_dataset(
    app_context: AppContext,
    *,
    dataset_id: str,
    org_id: str,
    labels: list[str],
    expected_samples: int,
) -> None:
    if app_context.injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    storage_factory = cast(
        DatasetStorageFactoryPort,
        app_context.injector.get(DatasetStorageFactoryPort),
    )
    storage = await storage_factory.open(dataset_id, org_id=org_id)
    rows = cast(
        Any,
        await storage.list_samples(
            return_lazyframe=True,
            with_labels=False,
            with_predictions=False,
        ),
    )
    sample_ids = [
        str(value)
        for value in (await rows.select("sample_id").collect_async()).get_column(
            "sample_id"
        )
    ]
    if len(sample_ids) != expected_samples:
        raise RuntimeError(
            "Benchmark Dataset sample count mismatch: "
            f"imported={expected_samples} readable={len(sample_ids)}"
        )
    created_at = datetime.now(UTC)
    annotation_batch = 1_000
    for start in range(0, len(sample_ids), annotation_batch):
        batch = sample_ids[start : start + annotation_batch]
        created = await storage.create_annotations(
            [
                Annotation(
                    sample_id=sample_id,
                    label=labels[(start + index) % len(labels)],
                    created_by="sc-runtime-data-path-benchmark",
                    created_at=created_at,
                )
                for index, sample_id in enumerate(batch)
            ]
        )
        if created != len(batch):
            raise RuntimeError(
                f"Benchmark annotation write created {created}, expected {len(batch)}"
            )


async def _delete_benchmark_dataset(
    app_context: AppContext,
    *,
    dataset_id: str,
    org_id: str,
) -> None:
    if app_context.injector is None:
        return
    storage_factory = cast(
        DatasetStorageFactoryPort,
        app_context.injector.get(DatasetStorageFactoryPort),
    )
    storage = await storage_factory.open(dataset_id, org_id=org_id)
    await storage.delete()


async def _run(args: argparse.Namespace) -> dict[str, object]:
    import ml_library

    load_config.cache_clear()
    app_context = build_flow_app_context(load_config())
    run_id = uuid4().hex[:12]
    benchmark_dataset_id: str | None = None
    model_uri: str | None = None
    source_dataset: Any = None
    original_injector: Any = None
    try:
        source_dataset = await _find_source_dataset(
            app_context,
            dataset_id=args.source_dataset_id,
            dataset_name=args.source_dataset_name,
        )
        if source_dataset.dataset_type != "image_sc":
            raise ValueError("Benchmark source must be an image_sc Dataset")
        org_id = str(source_dataset.org_id or "")

        setup_started = time.perf_counter()
        benchmark_dataset_id, imported_samples = await _create_benchmark_dataset(
            app_context,
            source_dataset=source_dataset,
            requested_samples=args.samples,
            run_id=run_id,
        )
        await _label_benchmark_dataset(
            app_context,
            dataset_id=benchmark_dataset_id,
            org_id=org_id,
            labels=[str(label) for label in source_dataset.task_spec.label_space],
            expected_samples=imported_samples,
        )
        setup_seconds = time.perf_counter() - setup_started

        original_injector = app_context.injector
        if original_injector is None:
            raise RuntimeError("AppContext injector was not initialized")
        materializer = _MeasuredMaterializer(
            cast(
                ScInspectionMaterializerPort,
                original_injector.get(ScInspectionMaterializerPort),
            )
        )
        training_repository = _BenchmarkTrainingRepository()
        prediction_job_id = f"benchmark-predict-{run_id}"
        prediction_repository = _BenchmarkPredictionRepository(
            PredictionJob(
                id=prediction_job_id,
                dataset_id=benchmark_dataset_id,
                model_id="pending-benchmark-model",
                status=JobStatus.QUEUED,
                created_by="sc-runtime-data-path-benchmark",
                target="sc.patch_image.v1",
                model_version="benchmark-v1",
                org_id=org_id,
            )
        )
        app_context.injector = cast(
            Any,
            _BenchmarkInjector(
                original_injector,
                training_repository=training_repository,
                prediction_repository=prediction_repository,
                materializer=materializer,
            ),
        )

        artifact_sink = _BenchmarkArtifactSink(app_context, run_id)
        training_context = TrainingRuntimeContext(
            app_context=app_context,
            job_id=f"benchmark-train-{run_id}",
            dataset_id=benchmark_dataset_id,
            trainer_id=_TRAINER_ID,
            created_by="sc-runtime-data-path-benchmark",
            org_id=org_id,
        )
        with patch.object(ml_library, "train_yolo", new=fake_train_yolo):
            training_started = time.perf_counter()
            training_result = await collect_runtime_events(
                runtime_ultralytics.yolo_sc_train(training_context),
                artifact_sink=artifact_sink,
            )
            training_seconds = time.perf_counter() - training_started

        artifact = artifact_sink.artifact
        if artifact is None:
            raise RuntimeError("Fake training emitted no model artifact")
        model_uri = artifact.uri
        prediction_repository.job = prediction_repository.job.model_copy(
            update={"model_id": artifact.id}
        )
        model = Model(
            **artifact.model_dump(),
            job_id=training_context.job_id,
            dataset_id=benchmark_dataset_id,
            trainer_id=_TRAINER_ID,
            created_by="sc-runtime-data-path-benchmark",
        )

        async def load_benchmark_model(_ctx: PredictionRuntimeContext) -> Model:
            return model

        prediction_context = PredictionRuntimeContext(
            app_context=app_context,
            job_id=prediction_job_id,
            dataset_id=benchmark_dataset_id,
            model_id=artifact.id,
            org_id=org_id,
            predictor_id=_PREDICTOR_ID,
            created_by="sc-runtime-data-path-benchmark",
            target="sc.patch_image.v1",
            model_version="benchmark-v1",
        )
        with (
            patch.object(
                ml_library,
                "predict_yolo_stream",
                new=fake_predict_yolo_stream,
            ),
            patch.object(
                runtime_ultralytics,
                "load_sc_prediction_model",
                new=load_benchmark_model,
            ),
        ):
            prediction_started = time.perf_counter()
            prediction_result = await collect_runtime_events(
                runtime_ultralytics.yolo_sc_predictor(prediction_context)
            )
            prediction_seconds = time.perf_counter() - prediction_started

        app_context.injector = original_injector
        storage_factory = cast(
            DatasetStorageFactoryPort,
            original_injector.get(DatasetStorageFactoryPort),
        )
        storage = await storage_factory.open(benchmark_dataset_id, org_id=org_id)
        persisted_predictions = await storage.list_predictions(
            job_id=prediction_job_id,
            limit=None,
        )
        processed = _required_int(prediction_result.get("processed"), "processed")
        failed = _required_int(prediction_result.get("failed"), "failed")
        if (
            processed != imported_samples
            or len(persisted_predictions) != imported_samples
        ):
            raise RuntimeError(
                "Prediction did not process and persist every sample: "
                f"imported={imported_samples} processed={processed} "
                f"persisted={len(persisted_predictions)}"
            )
        if failed:
            raise RuntimeError(
                f"Prediction image resolution failed for {failed} samples"
            )

        measurement = materializer.measurement
        training_metrics = training_result.get("metrics", {})
        trained_samples = _required_int(
            training_metrics.get("num_samples")
            if isinstance(training_metrics, Mapping)
            else None,
            "training.metrics.num_samples",
        )
        consumed_input_bytes = _required_int(
            training_metrics.get("input_bytes")
            if isinstance(training_metrics, Mapping)
            else None,
            "training.metrics.input_bytes",
        )
        if trained_samples != measurement.rows:
            raise RuntimeError(
                "Fake Trainer did not consume every materialized row: "
                f"materialized={measurement.rows} consumed={trained_samples}"
            )
        return {
            "run_id": run_id,
            "source_dataset_id": source_dataset.id,
            "benchmark_dataset_id": benchmark_dataset_id,
            "dataset_samples": imported_samples,
            "setup_seconds": round(setup_seconds, 6),
            "training": {
                "materialized_samples": measurement.rows,
                "materialized_bytes": measurement.bytes,
                "materialization_errors": measurement.errors,
                "materialization_seconds": round(
                    measurement.elapsed_seconds,
                    6,
                ),
                "materialization_samples_per_second": round(
                    measurement.rows / measurement.elapsed_seconds,
                    2,
                ),
                "runtime_seconds": round(training_seconds, 6),
                "runtime_samples_per_second": round(
                    trained_samples / training_seconds,
                    2,
                ),
                "consumed_samples": trained_samples,
                "consumed_input_bytes": consumed_input_bytes,
                "event_count": len(training_repository.events),
            },
            "prediction": {
                "processed_samples": processed,
                "persisted_samples": len(persisted_predictions),
                "failed_samples": failed,
                "runtime_seconds": round(prediction_seconds, 6),
                "runtime_samples_per_second": round(
                    processed / prediction_seconds,
                    2,
                ),
                "event_count": len(prediction_repository.events),
            },
        }
    finally:
        if original_injector is not None:
            app_context.injector = original_injector
        if model_uri is not None:
            try:
                await app_context.shared.artifact_storage.delete(model_uri)
            except FileNotFoundError:
                pass
        if benchmark_dataset_id is not None and source_dataset is not None:
            await _delete_benchmark_dataset(
                app_context,
                dataset_id=benchmark_dataset_id,
                org_id=str(source_dataset.org_id or ""),
            )
        await close_flow_app_context(app_context)


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return value


def _positive_float(raw: str) -> float:
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return value


def _required_int(value: object, name: str) -> int:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise RuntimeError(f"Benchmark result {name!r} is not numeric: {value!r}")
    return int(value)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark the real SC training materialization and prediction stream "
            "from Runtime entry to completion with GPU kernels replaced by fakes."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-dataset-id")
    source.add_argument("--source-dataset-name")
    parser.add_argument("--samples", type=_positive_int, required=True)
    parser.add_argument(
        "--minimum-training-samples-per-second",
        type=_positive_float,
    )
    parser.add_argument(
        "--minimum-prediction-samples-per-second",
        type=_positive_float,
    )
    return parser.parse_args()


def _enforce_minimums(result: dict[str, object], args: argparse.Namespace) -> None:
    checks = (
        (
            "training materialization",
            cast(dict[str, object], result["training"])[
                "materialization_samples_per_second"
            ],
            args.minimum_training_samples_per_second,
        ),
        (
            "prediction runtime",
            cast(dict[str, object], result["prediction"])["runtime_samples_per_second"],
            args.minimum_prediction_samples_per_second,
        ),
    )
    for name, actual_raw, minimum in checks:
        if minimum is None:
            continue
        actual = float(cast(float | int, actual_raw))
        if actual < minimum:
            raise RuntimeError(
                f"{name} throughput below minimum: {actual:.2f} < {minimum:.2f}"
            )


def main() -> int:
    args = _parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, sort_keys=True))
    _enforce_minimums(result, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
