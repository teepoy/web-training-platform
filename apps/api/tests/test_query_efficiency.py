"""Regression tests for bounded list-query counts.

The counts deliberately do not grow with the number of returned rows. This
guards paginated list endpoints against reintroducing enrichment N+1 reads.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import app
from app.shared.api.schemas import (
    JobStatus,
    PlatformPrediction,
    PredictionCollection,
    PredictionCollectionItem,
    PredictionJob,
    TrainingJob,
)
from tests.conftest import (
    DEFAULT_ORG_ID,
    DEFAULT_USER_ID,
    TRAINER_ID,
    create_dataset,
)


def _count_selects(engine, operation: Callable[[], object]) -> int:
    select_count = 0

    def before_cursor_execute(
        _conn,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        operation()
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
    return select_count


def test_dataset_page_uses_two_selects_for_many_rows() -> None:
    with TestClient(app) as client:
        for index in range(8):
            create_dataset(client, name=f"query-dataset-{index}")

        context = app.state.app_context
        response = None

        def load() -> None:
            nonlocal response
            response = client.get("/api/v1/datasets?offset=0&limit=8")

        count = _count_selects(
            context.shared.db_engine.sync_engine,
            load,
        )
        assert response is not None
        assert response.status_code == 200
        assert len(response.json()["items"]) == response.json()["total"] == 8
        assert count == 2


def test_prediction_job_page_uses_two_selects_for_many_rows() -> None:
    with TestClient(app) as client:
        dataset_id = create_dataset(client, name="prediction-query-count")
        context = app.state.app_context
        repository = context.prediction.prediction_repository

        async def seed() -> None:
            for index in range(8):
                await repository.create_prediction_job(
                    PredictionJob(
                        id=f"query-prediction-{index}",
                        org_id=DEFAULT_ORG_ID,
                        dataset_id=dataset_id,
                        model_id=f"model-{index}",
                        status=JobStatus.COMPLETED,
                        created_by=DEFAULT_USER_ID,
                    ),
                    org_id=DEFAULT_ORG_ID,
                )

        asyncio.run(seed())

        async def load() -> None:
            rows, total = await repository.list_prediction_jobs_paginated(
                org_id=DEFAULT_ORG_ID,
                dataset_id=dataset_id,
                offset=0,
                limit=8,
            )
            assert len(rows) == total == 8

        count = _count_selects(
            context.shared.db_engine.sync_engine,
            lambda: asyncio.run(load()),
        )
        assert count == 2


def test_prediction_collection_page_uses_three_selects_for_many_rows() -> None:
    with TestClient(app) as client:
        dataset_id = create_dataset(client, name="prediction-collection-query-count")
        context = app.state.app_context
        repository = context.prediction.prediction_repository

        async def seed() -> None:
            predictions = [
                PlatformPrediction(
                    id=f"query-collection-prediction-{index}",
                    org_id=DEFAULT_ORG_ID,
                    dataset_id=dataset_id,
                    sample_id=f"sample-{index}",
                    model_id="model-1",
                    predicted_label="cat",
                    created_by=DEFAULT_USER_ID,
                )
                for index in range(8)
            ]
            await repository.create_platform_predictions_bulk(predictions)
            for index, prediction in enumerate(predictions):
                collection = PredictionCollection(
                    id=f"query-collection-{index}",
                    org_id=DEFAULT_ORG_ID,
                    dataset_id=dataset_id,
                    model_id="model-1",
                    name=f"Collection {index}",
                    created_by=DEFAULT_USER_ID,
                )
                await repository.create_prediction_collection(collection)
                await repository.add_prediction_collection_items(
                    [
                        PredictionCollectionItem(
                            collection_id=collection.id,
                            prediction_id=prediction.id,
                        )
                    ]
                )

        asyncio.run(seed())

        async def load() -> None:
            collections, total = (
                await repository.list_prediction_collections_paginated(
                    dataset_id,
                    DEFAULT_ORG_ID,
                    offset=0,
                    limit=50,
                )
            )
            prediction_ids = await repository.list_prediction_ids_by_collection(
                [collection.id for collection in collections],
                DEFAULT_ORG_ID,
            )
            assert total == len(collections) == len(prediction_ids) == 8
            assert all(len(ids) == 1 for ids in prediction_ids.values())

        count = _count_selects(
            context.shared.db_engine.sync_engine,
            lambda: asyncio.run(load()),
        )
        # One count, one page query, and one bulk collection-item query.
        assert count == 3


def test_prediction_id_batch_lookup_uses_one_select_for_many_rows() -> None:
    with TestClient(app) as client:
        dataset_id = create_dataset(client, name="prediction-id-query-count")
        context = app.state.app_context
        repository = context.prediction.prediction_repository
        predictions = [
            PlatformPrediction(
                id=f"query-id-prediction-{index}",
                org_id=DEFAULT_ORG_ID,
                dataset_id=dataset_id,
                sample_id=f"sample-{index}",
                model_id="model-1",
                predicted_label="cat",
                created_by=DEFAULT_USER_ID,
            )
            for index in range(8)
        ]
        asyncio.run(repository.create_platform_predictions_bulk(predictions))

        async def load() -> None:
            rows = await repository.get_platform_predictions_by_ids(
                [prediction.id for prediction in predictions],
                DEFAULT_ORG_ID,
            )
            assert set(rows) == {prediction.id for prediction in predictions}

        count = _count_selects(
            context.shared.db_engine.sync_engine,
            lambda: asyncio.run(load()),
        )
        assert count == 1


def test_training_job_page_uses_three_selects_for_many_rows() -> None:
    with TestClient(app) as client:
        dataset_id = create_dataset(client, name="training-query-count")
        context = app.state.app_context
        repository = context.training.repository

        async def seed() -> None:
            for index in range(8):
                await repository.create_job(
                    TrainingJob(
                        id=f"query-training-{index}",
                        org_id=DEFAULT_ORG_ID,
                        dataset_id=dataset_id,
                        trainer_id=TRAINER_ID,
                        status=JobStatus.COMPLETED,
                        created_by=DEFAULT_USER_ID,
                    )
                )

        asyncio.run(seed())

        async def load() -> None:
            rows, total = await repository.list_jobs_paginated(
                org_id=DEFAULT_ORG_ID,
                dataset_id=dataset_id,
                offset=0,
                limit=8,
            )
            assert len(rows) == total == 8

        count = _count_selects(
            context.shared.db_engine.sync_engine,
            lambda: asyncio.run(load()),
        )
        assert count == 3


def test_training_job_summary_page_skips_artifact_select() -> None:
    with TestClient(app) as client:
        dataset_id = create_dataset(client, name="training-summary-query-count")
        context = app.state.app_context
        repository = context.training.repository

        async def seed() -> None:
            for index in range(8):
                await repository.create_job(
                    TrainingJob(
                        id=f"query-training-summary-{index}",
                        org_id=DEFAULT_ORG_ID,
                        dataset_id=dataset_id,
                        trainer_id=TRAINER_ID,
                        status=JobStatus.COMPLETED,
                        created_by=DEFAULT_USER_ID,
                    )
                )

        asyncio.run(seed())

        async def load() -> None:
            rows, total = await repository.list_jobs_paginated(
                org_id=DEFAULT_ORG_ID,
                dataset_id=dataset_id,
                offset=0,
                limit=8,
                include_artifacts=False,
            )
            assert len(rows) == total == 8
            assert all(not row.artifact_refs for row in rows)

        count = _count_selects(
            context.shared.db_engine.sync_engine,
            lambda: asyncio.run(load()),
        )
        assert count == 2
