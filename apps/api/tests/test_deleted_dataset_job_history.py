from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.api.schemas import JobStatus, PredictionJob, TrainingJob
from app.shared.db.models.prediction import PredictionJobORM
from app.shared.db.models.training import TrainingJobORM
from tests.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, TRAINER_ID

pytestmark = pytest.mark.integration


def test_delete_dataset_rejects_active_training_and_prediction_jobs() -> None:
    suffix = uuid4().hex
    training_job_id = f"active-dataset-training-{suffix}"
    prediction_job_id = f"active-dataset-prediction-{suffix}"

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/datasets",
            json={
                "name": f"active-dataset-job-guard-{suffix}",
                "dataset_type": "image_classification",
                "task_spec": {
                    "task_type": "classification",
                    "label_space": ["cat", "dog"],
                },
            },
        )
        assert created.status_code == 200, created.text
        dataset_id = created.json()["id"]

        async def seed_active_jobs() -> None:
            await app.state.app_context.training.repository.create_job(
                TrainingJob(
                    id=training_job_id,
                    org_id=DEFAULT_ORG_ID,
                    dataset_id=dataset_id,
                    trainer_id=TRAINER_ID,
                    status=JobStatus.QUEUED,
                    created_by=DEFAULT_USER_ID,
                )
            )
            await app.state.app_context.prediction.prediction_repository.create_prediction_job(
                PredictionJob(
                    id=prediction_job_id,
                    org_id=DEFAULT_ORG_ID,
                    dataset_id=dataset_id,
                    model_id="active-source-model",
                    status=JobStatus.RUNNING,
                    created_by=DEFAULT_USER_ID,
                )
            )

        asyncio.run(seed_active_jobs())

        blocked = client.delete(f"/api/v1/datasets/{dataset_id}")
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["detail"] == (
            "Dataset cannot be deleted while training and prediction jobs "
            "are queued or running"
        )

        async def finish_jobs() -> None:
            await app.state.app_context.training.repository.update_job_status(
                training_job_id, JobStatus.CANCELLED
            )
            await app.state.app_context.prediction.prediction_repository.update_prediction_job_status(
                prediction_job_id, JobStatus.COMPLETED
            )

        asyncio.run(finish_jobs())

        deleted = client.delete(f"/api/v1/datasets/{dataset_id}")
        assert deleted.status_code == 204, deleted.text


def test_deleted_dataset_keeps_job_history_readable() -> None:
    """A deleted source dataset must not make historical job APIs fail."""
    suffix = uuid4().hex
    training_job_id = f"deleted-dataset-training-{suffix}"
    prediction_job_id = f"deleted-dataset-prediction-{suffix}"

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/datasets",
            json={
                "name": f"deleted-dataset-job-history-{suffix}",
                "dataset_type": "image_classification",
                "task_spec": {
                    "task_type": "classification",
                    "label_space": ["cat", "dog"],
                },
            },
        )
        assert created.status_code == 200, created.text
        dataset_id = created.json()["id"]

        async def seed_jobs() -> None:
            await app.state.app_context.training.repository.create_job(
                TrainingJob(
                    id=training_job_id,
                    org_id=DEFAULT_ORG_ID,
                    dataset_id=dataset_id,
                    trainer_id=TRAINER_ID,
                    status=JobStatus.FAILED,
                    created_by=DEFAULT_USER_ID,
                )
            )
            await app.state.app_context.prediction.prediction_repository.create_prediction_job(
                PredictionJob(
                    id=prediction_job_id,
                    org_id=DEFAULT_ORG_ID,
                    dataset_id=dataset_id,
                    model_id="deleted-source-model",
                    status=JobStatus.FAILED,
                    created_by=DEFAULT_USER_ID,
                )
            )

        asyncio.run(seed_jobs())

        deleted = client.delete(f"/api/v1/datasets/{dataset_id}")
        assert deleted.status_code == 204, deleted.text

        async def simulate_postgres_set_null() -> None:
            # The test profile uses SQLite without FK enforcement. Production
            # PostgreSQL applies the migration's ON DELETE SET NULL itself.
            async with app.state.app_context.shared.session_factory() as session:
                training_row = await session.get(TrainingJobORM, training_job_id)
                prediction_row = await session.get(PredictionJobORM, prediction_job_id)
                assert training_row is not None
                assert prediction_row is not None
                training_row.dataset_id = None
                prediction_row.dataset_id = None
                await session.commit()

        asyncio.run(simulate_postgres_set_null())

        training_detail = client.get(f"/api/v1/training-jobs/{training_job_id}")
        assert training_detail.status_code == 200, training_detail.text
        assert training_detail.json()["dataset_id"] is None

        prediction_detail = client.get(
            f"/api/v1/prediction-jobs/{prediction_job_id}"
        )
        assert prediction_detail.status_code == 200, prediction_detail.text
        assert prediction_detail.json()["dataset_id"] is None

        training_list = client.get("/api/v1/training-jobs")
        assert training_list.status_code == 200, training_list.text
        assert next(
            item
            for item in training_list.json()["items"]
            if item["id"] == training_job_id
        )["dataset_id"] is None

        prediction_list = client.get("/api/v1/prediction-jobs")
        assert prediction_list.status_code == 200, prediction_list.text
        assert next(
            item
            for item in prediction_list.json()["items"]
            if item["id"] == prediction_job_id
        )["dataset_id"] is None

        dashboard = client.get("/api/v1/dashboard")
        assert dashboard.status_code == 200, dashboard.text
        assert next(
            item
            for item in dashboard.json()["recent_jobs"]
            if item["id"] == training_job_id
        )["dataset_id"] is None

        tasks = client.get("/api/v1/task-tracker/tasks")
        assert tasks.status_code == 200, tasks.text
        history = {
            item["id"]: item["dataset_id"] for item in tasks.json()["items"]
        }
        assert history[training_job_id] is None
        assert history[prediction_job_id] is None
