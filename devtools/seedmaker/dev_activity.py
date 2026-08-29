from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.db.models.artifacts import ArtifactORM
from app.shared.db.models.prediction import PredictionEventORM, PredictionJobORM
from app.shared.db.models.training import TrainingEventORM, TrainingJobORM
from app.shared.infrastructure.storage.base import ArtifactStorage


@dataclass(frozen=True, slots=True)
class DevActivityContext:
    org_id: str
    created_by: str
    sc_dataset_id: str
    sc_collection_id: str
    sc_collection_revision_id: str
    label_space: tuple[str, ...]
    sc_sample_count: int
    sc_annotation_count: int


@dataclass(frozen=True, slots=True)
class DevActivitySummary:
    training_jobs: int
    prediction_jobs: int
    models: int


TRAINING_JOB_IDS = (
    "dev-seed-train-completed",
    "dev-seed-train-collection",
    "dev-seed-train-failed",
    "dev-seed-train-cancelled",
)
PREDICTION_JOB_IDS = (
    "dev-seed-predict-completed",
    "dev-seed-predict-collection",
    "dev-seed-predict-failed",
    "dev-seed-predict-cancelled",
)
MODEL_IDS = (
    "dev-seed-model-dataset",
    "dev-seed-model-collection",
)


async def seed_dev_activity(
    session_factory: async_sessionmaker[AsyncSession],
    storage: ArtifactStorage,
    context: DevActivityContext,
    *,
    now: datetime | None = None,
) -> DevActivitySummary:
    """Converge deterministic, non-executing activity records for dev pages.

    These records have no external execution IDs, so no Prefect run is submitted.
    Re-running replaces events owned by the fixed ``dev-seed-*`` IDs and leaves
    unrelated records untouched.
    """

    timestamp = now or datetime.now(UTC)
    jobs = _training_jobs(context, timestamp)
    prediction_jobs = _prediction_jobs(context, timestamp)

    async with session_factory() as session:
        for job in jobs:
            await session.merge(job)
        await session.flush()

        await session.execute(
            delete(TrainingEventORM).where(
                TrainingEventORM.job_id.in_(TRAINING_JOB_IDS)
            )
        )
        session.add_all(_training_events(context, timestamp))

        models = await _model_artifacts(storage, context, timestamp)
        for model in models:
            await session.merge(model)
        for metrics in await _metric_artifacts(storage, context, timestamp):
            await session.merge(metrics)

        for job in prediction_jobs:
            await session.merge(job)
        await session.flush()
        await session.execute(
            delete(PredictionEventORM).where(
                PredictionEventORM.job_id.in_(PREDICTION_JOB_IDS)
            )
        )
        session.add_all(_prediction_events(context, timestamp))
        await session.commit()

    return DevActivitySummary(
        training_jobs=len(jobs),
        prediction_jobs=len(prediction_jobs),
        models=len(models),
    )


def _training_jobs(
    context: DevActivityContext,
    now: datetime,
) -> list[TrainingJobORM]:
    shared = {
        "org_id": context.org_id,
        "trainer_id": "yolo-sc-v1",
        "is_public": False,
        "created_by": context.created_by,
        "user_id": context.created_by,
        "external_job_id": None,
    }
    return [
        TrainingJobORM(
            id=TRAINING_JOB_IDS[0],
            dataset_id=context.sc_dataset_id,
            collection_id=None,
            collection_revision_id=None,
            status="completed",
            created_at=now - timedelta(days=3, hours=2),
            updated_at=now - timedelta(days=3),
            **shared,
        ),
        TrainingJobORM(
            id=TRAINING_JOB_IDS[1],
            dataset_id=None,
            collection_id=context.sc_collection_id,
            collection_revision_id=context.sc_collection_revision_id,
            status="completed",
            created_at=now - timedelta(days=2, hours=3),
            updated_at=now - timedelta(days=2),
            **shared,
        ),
        TrainingJobORM(
            id=TRAINING_JOB_IDS[2],
            dataset_id=context.sc_dataset_id,
            collection_id=None,
            collection_revision_id=None,
            status="failed",
            created_at=now - timedelta(days=1, hours=2),
            updated_at=now - timedelta(days=1, hours=1, minutes=47),
            **shared,
        ),
        TrainingJobORM(
            id=TRAINING_JOB_IDS[3],
            dataset_id=context.sc_dataset_id,
            collection_id=None,
            collection_revision_id=None,
            status="cancelled",
            created_at=now - timedelta(hours=9),
            updated_at=now - timedelta(hours=8, minutes=52),
            **shared,
        ),
    ]


def _training_events(
    context: DevActivityContext,
    now: datetime,
) -> list[TrainingEventORM]:
    return [
        TrainingEventORM(
            job_id=TRAINING_JOB_IDS[0],
            ts=now - timedelta(days=3, hours=1, minutes=45),
            level="info",
            message="Dataset readiness check completed",
            payload={
                "active_classes": len(context.label_space),
                "annotated_samples": context.sc_annotation_count,
            },
        ),
        TrainingEventORM(
            job_id=TRAINING_JOB_IDS[0],
            ts=now - timedelta(days=3, minutes=8),
            level="metric",
            message="Training metrics recorded",
            payload={"accuracy": 0.91, "f1_macro": 0.89, "epochs": 50},
        ),
        TrainingEventORM(
            job_id=TRAINING_JOB_IDS[0],
            ts=now - timedelta(days=3),
            level="info",
            message="Training completed and model artifact persisted",
            payload={"model_id": MODEL_IDS[0]},
        ),
        TrainingEventORM(
            job_id=TRAINING_JOB_IDS[1],
            ts=now - timedelta(days=2, hours=2, minutes=45),
            level="info",
            message="Collection revision resolved",
            payload={"source": "dataset_collection_revision"},
        ),
        TrainingEventORM(
            job_id=TRAINING_JOB_IDS[1],
            ts=now - timedelta(days=2),
            level="info",
            message="Collection training completed",
            payload={"model_id": MODEL_IDS[1]},
        ),
        TrainingEventORM(
            job_id=TRAINING_JOB_IDS[2],
            ts=now - timedelta(days=1, hours=1, minutes=47),
            level="error",
            message="Demo failure: unreadable patch images exceeded the run budget",
            payload={"code": "seed_demo_unreadable_images"},
        ),
        TrainingEventORM(
            job_id=TRAINING_JOB_IDS[3],
            ts=now - timedelta(hours=8, minutes=52),
            level="warning",
            message="Demo run cancelled by operator",
            payload={"reason": "manual_cancel"},
        ),
    ]


async def _model_artifacts(
    storage: ArtifactStorage,
    context: DevActivityContext,
    now: datetime,
) -> list[ArtifactORM]:
    definitions = (
        (
            MODEL_IDS[0],
            TRAINING_JOB_IDS[0],
            "Dev SC Baseline (display fixture)",
            context.sc_dataset_id,
            None,
            None,
            now - timedelta(days=3),
        ),
        (
            MODEL_IDS[1],
            TRAINING_JOB_IDS[1],
            "Dev SC Collection Model (display fixture)",
            None,
            context.sc_collection_id,
            context.sc_collection_revision_id,
            now - timedelta(days=2),
        ),
    )
    artifacts: list[ArtifactORM] = []
    for (
        artifact_id,
        job_id,
        name,
        dataset_id,
        collection_id,
        revision_id,
        created_at,
    ) in definitions:
        payload = json.dumps(
            {
                "fixture": "dev-seed",
                "artifact_id": artifact_id,
                "note": "Metadata-only display fixture; do not use for inference.",
            },
            sort_keys=True,
        ).encode()
        uri = await storage.put_bytes(
            f"dev-seed/models/{artifact_id}.json",
            payload,
            "application/json",
        )
        artifacts.append(
            ArtifactORM(
                id=artifact_id,
                job_id=job_id,
                uri=uri,
                kind="model",
                metadata_json={
                    "seed_fixture": True,
                    "runnable": False,
                    "trainer_id": "yolo-sc-v1",
                    "predictor_ids": ["yolo-sc-v1"],
                    "model_contract": "sc.yolo.model.v1",
                    "model_schema_version": "1",
                    "label_space": list(context.label_space),
                    "source_dataset_id": dataset_id,
                    "source_collection_id": collection_id,
                    "source_collection_revision_id": revision_id,
                },
                name=name,
                file_size=len(payload),
                file_hash=hashlib.sha256(payload).hexdigest(),
                format="json",
                created_at=created_at,
            )
        )
    return artifacts


async def _metric_artifacts(
    storage: ArtifactStorage,
    context: DevActivityContext,
    now: datetime,
) -> list[ArtifactORM]:
    del context
    definitions = (
        (
            "dev-seed-metrics-dataset",
            TRAINING_JOB_IDS[0],
            {"accuracy": 0.91, "f1_macro": 0.89, "loss": 0.24},
            now - timedelta(days=3),
        ),
        (
            "dev-seed-metrics-collection",
            TRAINING_JOB_IDS[1],
            {"accuracy": 0.88, "f1_macro": 0.86, "loss": 0.31},
            now - timedelta(days=2),
        ),
    )
    artifacts: list[ArtifactORM] = []
    for artifact_id, job_id, metrics, created_at in definitions:
        payload = json.dumps(metrics, sort_keys=True).encode()
        uri = await storage.put_bytes(
            f"dev-seed/metrics/{artifact_id}.json",
            payload,
            "application/json",
        )
        artifacts.append(
            ArtifactORM(
                id=artifact_id,
                job_id=job_id,
                uri=uri,
                kind="metrics",
                metadata_json={"seed_fixture": True, **metrics},
                name=f"{artifact_id}.json",
                file_size=len(payload),
                file_hash=hashlib.sha256(payload).hexdigest(),
                format="json",
                created_at=created_at,
            )
        )
    return artifacts


def _prediction_jobs(
    context: DevActivityContext,
    now: datetime,
) -> list[PredictionJobORM]:
    failed_processed = min(context.sc_sample_count, 420)
    failed_count = min(failed_processed, 4)
    cancelled_processed = min(context.sc_sample_count, 128)
    shared = {
        "org_id": context.org_id,
        "target": "sc_defect_classification",
        "model_version": "dev-seed-v1",
        "sample_ids": None,
        "created_by": context.created_by,
        "external_job_id": None,
    }
    return [
        PredictionJobORM(
            id=PREDICTION_JOB_IDS[0],
            dataset_id=context.sc_dataset_id,
            dataset_collection_id=None,
            dataset_collection_revision_id=None,
            model_id=MODEL_IDS[0],
            status="completed",
            summary_json={
                "total_samples": context.sc_sample_count,
                "processed": context.sc_sample_count,
                "successful": max(0, context.sc_sample_count - 13),
                "failed": min(13, context.sc_sample_count),
                "seed_fixture": True,
            },
            created_at=now - timedelta(days=2, hours=4),
            updated_at=now - timedelta(days=2, hours=3, minutes=42),
            **shared,
        ),
        PredictionJobORM(
            id=PREDICTION_JOB_IDS[1],
            dataset_id=None,
            dataset_collection_id=context.sc_collection_id,
            dataset_collection_revision_id=context.sc_collection_revision_id,
            model_id=MODEL_IDS[1],
            status="completed",
            summary_json={
                "total_samples": context.sc_sample_count,
                "processed": context.sc_sample_count,
                "successful": context.sc_sample_count,
                "failed": 0,
                "seed_fixture": True,
            },
            created_at=now - timedelta(days=1, hours=6),
            updated_at=now - timedelta(days=1, hours=5, minutes=39),
            **shared,
        ),
        PredictionJobORM(
            id=PREDICTION_JOB_IDS[2],
            dataset_id=context.sc_dataset_id,
            dataset_collection_id=None,
            dataset_collection_revision_id=None,
            model_id=MODEL_IDS[0],
            status="failed",
            summary_json={
                "total_samples": context.sc_sample_count,
                "processed": failed_processed,
                "successful": failed_processed - failed_count,
                "failed": failed_count,
                "error": "Demo failure: worker capacity unavailable",
                "seed_fixture": True,
            },
            created_at=now - timedelta(hours=12),
            updated_at=now - timedelta(hours=11, minutes=51),
            **shared,
        ),
        PredictionJobORM(
            id=PREDICTION_JOB_IDS[3],
            dataset_id=context.sc_dataset_id,
            dataset_collection_id=None,
            dataset_collection_revision_id=None,
            model_id=MODEL_IDS[0],
            status="cancelled",
            summary_json={
                "total_samples": context.sc_sample_count,
                "processed": cancelled_processed,
                "successful": cancelled_processed,
                "failed": 0,
                "seed_fixture": True,
            },
            created_at=now - timedelta(hours=4),
            updated_at=now - timedelta(hours=3, minutes=57),
            **shared,
        ),
    ]


def _prediction_events(
    context: DevActivityContext,
    now: datetime,
) -> list[PredictionEventORM]:
    return [
        PredictionEventORM(
            job_id=PREDICTION_JOB_IDS[0],
            ts=now - timedelta(days=2, hours=4),
            level="info",
            message="Prediction started",
            payload={"total_samples": context.sc_sample_count},
        ),
        PredictionEventORM(
            job_id=PREDICTION_JOB_IDS[0],
            ts=now - timedelta(days=2, hours=3, minutes=42),
            level="info",
            message="Prediction completed with recoverable image errors",
            payload={
                "successful": max(0, context.sc_sample_count - 13),
                "failed": min(13, context.sc_sample_count),
            },
        ),
        PredictionEventORM(
            job_id=PREDICTION_JOB_IDS[1],
            ts=now - timedelta(days=1, hours=5, minutes=39),
            level="info",
            message="Collection prediction completed",
            payload={"successful": context.sc_sample_count},
        ),
        PredictionEventORM(
            job_id=PREDICTION_JOB_IDS[2],
            ts=now - timedelta(hours=11, minutes=51),
            level="error",
            message="Demo failure: worker capacity unavailable",
            payload={"code": "seed_demo_worker_unavailable"},
        ),
        PredictionEventORM(
            job_id=PREDICTION_JOB_IDS[3],
            ts=now - timedelta(hours=3, minutes=57),
            level="warning",
            message="Demo prediction cancelled by operator",
            payload={"reason": "manual_cancel"},
        ),
    ]
