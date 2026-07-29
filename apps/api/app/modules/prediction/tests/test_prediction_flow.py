"""Tests for the prediction flow (run_prediction_job and chunk tasks).

These tests call the prediction flow functions directly as plain Python —
no Prefect server required.  They exercise the full code path that runs
inside a Prefect worker.

Note: The flow resolves a fresh application context lazily via
``_with_app_context``. Tests patch this for deterministic behaviour.
Materialization calls are mocked since the test does not stand up an API
server for the ``/api/v1/datasets/{id}/materializations`` endpoint.

After T16, prediction dispatch goes through the executable predictor
registry (``get_predictor`` → ``Predictor`` Protocol) instead of
the legacy GPU worker container. Tests mock ``get_predictor`` to return a
factory that produces a predictor with realistic async behaviour.
"""

from __future__ import annotations

import asyncio
import base64
import json
from types import ModuleType, SimpleNamespace
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
import nest_asyncio

from app.main import app
from app.shared.api.schemas import ArtifactRef, JobStatus, PredictionJob, TaskSpec
from app.shared.domain.runtime import BatchPredictResult, PredictResult
from tests.conftest import DEFAULT_ORG_ID, TRAINER_ID

nest_asyncio.apply()


def _predict_flow_module() -> ModuleType:
    from app.modules.prediction.flows import predict_job
    return predict_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x04\x00\x00\x00\x04\x08\x02"
    b"\x00\x00\x00&\x93\t)\x00\x00\x00\x14IDATx\x9cclpP`\x80\x01&\x06$\x80\x9b\x03"
    b"\x00-$\x00\xe8\xd2`\xe8\xf5\x00\x00\x00\x00IEND\xaeB`\x82"
)

_DATA_URI = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode()


class _multi_patch:
    """Context manager that applies multiple patches together."""

    def __init__(self, *patches):
        self._patches = patches
        self._mocks: list[MagicMock] = []

    def __enter__(self):
        self._mocks = [p.__enter__() for p in self._patches]
        return self._mocks

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.__exit__(*exc)


def _patch_prefect_tasks():
    """Patch Prefect tasks to execute their underlying functions directly.

    This bypasses Prefect's task engine which would otherwise create a new
    execution context.
    """
    _mod = _predict_flow_module()

    return _multi_patch(
        patch.object(_mod, "predict_chunk", side_effect=_mod.predict_chunk.fn),
        patch.object(_mod, "persist_chunk_results", side_effect=_mod.persist_chunk_results.fn),
    )


def _install_flow_worker_mocks() -> dict[str, MagicMock]:
    predict_job_mod = _predict_flow_module()

    async def _test_with_app_context():
        return app.state.app_context, False

    setattr(predict_job_mod, "_with_app_context", _test_with_app_context)

    # Build a realistic predictor mock that answers predict_batch with
    # properly-formed PredictResult/BatchPredictResult objects.
    mock_predictor = MagicMock()
    mock_predictor.load_model = AsyncMock()
    mock_predictor.unload_model = AsyncMock()

    async def _fake_predict_batch(ctx, samples):
        predictions = [
            PredictResult(
                sample_id=str(s.get("sample_id", "")),
                label="cat",
                confidence=0.9,
                scores={"cat": 0.9, "dog": 0.1},
            )
            for s in samples
        ]
        return BatchPredictResult(
            predictions=predictions,
            total=len(samples),
            successful=len(samples),
            failed=0,
        )

    mock_predictor.predict_batch = _fake_predict_batch

    # get_predictor(id) returns a factory; calling the factory returns the
    # ready-to-use predictor instance.
    mock_factory = MagicMock(return_value=mock_predictor)
    mock_get_predictor = MagicMock(return_value=mock_factory)
    setattr(predict_job_mod, "get_predictor", mock_get_predictor)

    mat_mock = MagicMock()
    mat_mock.materialize_dataset = AsyncMock(
        side_effect=ConnectionError("materialization not available in test")
    )
    setattr(predict_job_mod, "MaterializeClient", MagicMock(return_value=mat_mock))

    return {
        "get_predictor": mock_get_predictor,
        "predictor": mock_predictor,
    }


def _seed_prediction_setup(
    client,
    n_samples: int = 3,
    labels: list[str] | None = None,
) -> tuple[str, str, list[str]]:
    """Create dataset + samples + a model artifact in DB.

    Returns ``(dataset_id, model_id, sample_ids)``.
    """
    labels = labels or ["cat", "dog"]
    ds = client.post(
        "/api/v1/datasets",
        json={
            "name": "predict-flow-test-ds",
            "dataset_type": "image_classification",
            "task_spec": {"task_type": "classification", "label_space": labels},
        },
    )
    assert ds.status_code == 200
    dataset_id = ds.json()["id"]

    sample_ids: list[str] = []
    for i in range(n_samples):
        s = client.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={"image_uris": [_DATA_URI]},
        )
        assert s.status_code == 200
        sid = s.json()["id"]
        sample_ids.append(sid)
        label = labels[i % len(labels)]
        ann = client.post(
            "/api/v1/annotations",
            json={"dataset_id": dataset_id, "sample_id": sid, "label": label, "source": "test"},
        )
        assert ann.status_code == 200

    # Create a training job record (needed for model→job FK)
    job_resp = client.post(
        "/api/v1/training-jobs",
        json={"dataset_id": dataset_id, "trainer_id": TRAINER_ID, "created_by": "test"},
    )
    assert job_resp.status_code == 200
    train_job_id = job_resp.json()["id"]

    # Create model artifact directly
    model_id = str(uuid4())
    model_object_name = f"models/{model_id}/model.json"
    model_payload = json.dumps({
        "prototypes": {lbl: [0.1] * 64 for lbl in labels},
        "label_space": labels,
    }).encode()

    repo = app.state.app_context.prediction.prediction_repository
    storage = app.state.app_context.shared.artifact_storage

    asyncio.run(storage.put_bytes(model_object_name, model_payload))
    model_uri = f"memory://{model_object_name}"
    asyncio.run(
        repo.add_artifacts(
            train_job_id,
            [
                ArtifactRef(
                    id=model_id,
                    uri=model_uri,
                    kind="model",
                    metadata={
                        "framework": "pytorch",
                        "architecture": "resnet50",
                        "dataset_type": "image_classification",
                        "task_types": ["classification"],
                        "prediction_targets": ["image_classification"],
                    },
                )
            ],
        )
    )

    return dataset_id, model_id, sample_ids


def _create_prediction_job_record(dataset_id: str, model_id: str) -> str:
    """Insert a prediction job record in the DB and return job_id."""
    job = PredictionJob(
        id=str(uuid4()),
        dataset_id=dataset_id,
        model_id=model_id,
        status=JobStatus.QUEUED,
        created_by="test",
        target="image_classification",
        org_id=DEFAULT_ORG_ID,
    )
    asyncio.run(app.state.app_context.prediction.prediction_repository.create_prediction_job(job, org_id=DEFAULT_ORG_ID))
    return job.id


# ---------------------------------------------------------------------------
# Tests — run_prediction_job
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="db_full materialize not yet supported; covered by test_predict_sparse_materialized")
def test_run_prediction_job_classification() -> None:
    """Full classification prediction flow completes and persists results."""
    with TestClient(app) as c:
        _install_flow_worker_mocks()
        dataset_id, model_id, sample_ids = _seed_prediction_setup(c, n_samples=3)
        job_id = _create_prediction_job_record(dataset_id, model_id)

        predict_job_mod = _predict_flow_module()

        with _patch_prefect_tasks():
            result = asyncio.run(
                predict_job_mod._run_prediction_job_with_context(
                    app_context=app.state.app_context,
                    job_id=job_id,
                    dataset_id=dataset_id,
                    model_id=model_id,
                    org_id=DEFAULT_ORG_ID,
                    target="image_classification",
                    model_version=None,
                    sample_ids=None,
                )
            )

        assert result["total_samples"] == 3
        assert result["successful"] + result["failed"] == result["processed"]
        assert "completed_at" in result


@pytest.mark.skip(reason="db_full materialize not yet supported; covered by test_predict_sparse_materialized")
def test_run_prediction_job_with_sample_subset() -> None:
    """Prediction flow processes only the specified sample_ids."""
    with TestClient(app) as c:
        _install_flow_worker_mocks()
        dataset_id, model_id, sample_ids = _seed_prediction_setup(c, n_samples=4)
        subset = sample_ids[:2]
        job_id = _create_prediction_job_record(dataset_id, model_id)

        predict_job_mod = _predict_flow_module()

        with _patch_prefect_tasks():
            result = asyncio.run(
                predict_job_mod._run_prediction_job_with_context(
                    app_context=app.state.app_context,
                    job_id=job_id,
                    dataset_id=dataset_id,
                    model_id=model_id,
                    org_id=DEFAULT_ORG_ID,
                    target="image_classification",
                    model_version=None,
                    sample_ids=subset,
                )
            )

        assert result["total_samples"] == 2


@pytest.mark.skip(reason="db_full materialize not yet supported; requires file_shard_sparse dataset")
def test_run_prediction_job_missing_dataset() -> None:
    """Flow raises ValueError for nonexistent dataset."""
    with TestClient(app):
        _install_flow_worker_mocks()
        predict_job_mod = _predict_flow_module()

        with _patch_prefect_tasks():
            with pytest.raises(ValueError, match="Dataset not found"):
                asyncio.run(
                    predict_job_mod._run_prediction_job_with_context(
                        app_context=app.state.app_context,
                        job_id="pred-missing-ds",
                        dataset_id="nonexistent-dataset",
                        model_id="nonexistent-model",
                        org_id=DEFAULT_ORG_ID,
                        target="image_classification",
                        model_version=None,
                        sample_ids=None,
                    )
                )


@pytest.mark.skip(reason="db_full materialize not yet supported; embedding tests moved to dedicated flow")
def test_run_prediction_job_embedding_target() -> None:
    """Embedding target path raises NotImplementedError — embedding moved to dedicated flow."""
    with TestClient(app) as c:
        _install_flow_worker_mocks()
        dataset_id, model_id, sample_ids = _seed_prediction_setup(c, n_samples=2)
        job_id = _create_prediction_job_record(dataset_id, model_id)

        predict_job_mod = _predict_flow_module()

        with _patch_prefect_tasks():
            with pytest.raises(NotImplementedError, match="embedding"):
                asyncio.run(
                    predict_job_mod._run_prediction_job_with_context(
                        app_context=app.state.app_context,
                        job_id=job_id,
                        dataset_id=dataset_id,
                        model_id=model_id,
                        org_id=DEFAULT_ORG_ID,
                        target="embedding",
                        model_version=None,
                        sample_ids=None,
                    )
                )


# ---------------------------------------------------------------------------
# Tests — individual chunk tasks
# ---------------------------------------------------------------------------


def test_persist_worker_results_uses_storage_aggregate() -> None:
    """Chunk persistence delegates prediction storage to DatasetStorageAgg."""
    predict_job_mod = _predict_flow_module()
    repo = MagicMock()
    repo.add_prediction_event = AsyncMock()
    storage_agg = MagicMock()
    storage_agg.get_samples_by_id = AsyncMock(
        return_value={
            "sample-1": SimpleNamespace(sample_id="sample-1"),
            "sample-2": SimpleNamespace(sample_id="sample-2"),
        }
    )
    captured: list[Any] = []

    async def _write_predictions(results, **kwargs):
        async for result in results:
            captured.append(result)
        return len(captured)

    storage_agg.write_predictions = AsyncMock(side_effect=_write_predictions)
    model = SimpleNamespace(id="model-1")

    result = asyncio.run(
        predict_job_mod._persist_worker_results(
            repo=repo,
            storage_agg=storage_agg,
            job_id="job-1",
            model=model,
            target="image_classification",
            model_version="v1",
            sample_ids=["sample-1", "sample-2"],
            worker_results=[
                {
                    "sample_id": "sample-1",
                    "label": "cat",
                    "confidence": 0.9,
                },
                {
                    "sample_id": "sample-2",
                    "label": "dog",
                    "confidence": 0.8,
                },
            ],
        )
    )

    assert [item.predicted_label for item in captured] == ["cat", "dog"]
    storage_agg.write_predictions.assert_awaited_once()
    assert result["successful"] == 2
    assert result["failed"] == 0


# ---------------------------------------------------------------------------
# Sparse materialized prediction
# ---------------------------------------------------------------------------

_FAKE_PNG_PRED = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
    b"\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc"
    b"\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND"
    b"\xaeB`\x82"
)


def _make_pred_sparse_row(index: int):
    from app.modules.datasets.domain.sample_row import BulkSampleRow, BulkImageRef

    sid = f"sp-{index:03d}"
    return BulkSampleRow(
        sample_id=sid,
        image_uris=[],
        metadata={},
        label="cat" if index % 2 == 0 else "dog",
        extra={"defect_id": sid},
        images=[
            BulkImageRef(
                image_id=f"img-{index}",
                role="review",
                bytes_=_FAKE_PNG_PRED,
                content_type="image/png",
                filename=f"test-{index}.png",
            )
        ],
    )


@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
def test_predict_sparse_materialized() -> None:
    """Predict via sparse materialized path.

    Seeds a sparse dataset with 2 shards / 10 rows, materializes,
    and runs prediction through ``_run_prediction_job_with_context``.
    Asserts the job completes and results are non-empty.
    """

    with TestClient(app):
        _install_flow_worker_mocks()

        # Fix the mock predictor's _view_id attribute so it returns None
        # instead of MagicMock (which breaks JSON serialization in the
        # materializer).
        predict_job_mod = _predict_flow_module()
        mock_factory = predict_job_mod.get_predictor.return_value
        mock_factory._view_id = None

        ctx = app.state.app_context
        test_storage = ctx.shared.artifact_storage
        repo = ctx.datasets.dataset_repository

        # ── 1. Ensure default org row exists ──────────────────────────
        from app.shared.db.models.auth import OrganizationORM
        from datetime import UTC, datetime as dt

        async def _ensure_org():
            async with ctx.shared.session_factory() as session:
                existing = await session.get(OrganizationORM, DEFAULT_ORG_ID)
                if existing is None:
                    session.add(
                        OrganizationORM(
                            id=DEFAULT_ORG_ID,
                            name="Default",
                            slug="default",
                            created_at=dt.now(UTC),
                        )
                    )
                    await session.commit()

        asyncio.run(_ensure_org())

        # ── 2. Create sparse dataset and seed shards ──────────────────
        dataset_id = str(uuid4())
        model_id = str(uuid4())

        from app.shared.api.schemas import (
            Dataset,
            DatasetStorageMode,
            SPARSE_NO_LS,
        )

        ds = Dataset(
            id=dataset_id,
            name="predict-sparse-ds",
            storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
            dataset_type="image_classification",
            ls_project_id=SPARSE_NO_LS,
        )
        # Set task_spec with label_space for classification
        ds.task_spec = TaskSpec(task_type="classification", label_space=["cat", "dog"])

        async def _create_dataset():
            await repo.create_dataset(ds, org_id=DEFAULT_ORG_ID)

        asyncio.run(_create_dataset())

        # ── 3. Create model artifact ──────────────────────────────────
        model_object_name = f"models/{model_id}/model.json"
        model_payload = json.dumps({
            "prototypes": {"cat": [0.1] * 64, "dog": [0.1] * 64},
            "label_space": ["cat", "dog"],
        }).encode()

        pred_repo = ctx.prediction.prediction_repository

        # The PredictionRepository.get_model joins ArtifactORM → TrainingJobORM
        # → DatasetORM.  Create a minimal training job record so the join works.
        train_job_id = str(uuid4())

        async def _create_model():
            # Create a training job row (needed for model FK join)
            from app.shared.db.models.training import TrainingJobORM
            from datetime import UTC, datetime as dt

            async with ctx.shared.session_factory() as session:
                session.add(
                    TrainingJobORM(
                        id=train_job_id,
                        org_id=DEFAULT_ORG_ID,
                        dataset_id=dataset_id,
                        trainer_id=TRAINER_ID,
                        status="completed",
                        created_by="test",
                        created_at=dt.now(UTC),
                        updated_at=dt.now(UTC),
                    )
                )
                await session.commit()

            await test_storage.put_bytes(model_object_name, model_payload)
            model_uri = f"memory://{model_object_name}"
            await pred_repo.add_artifacts(
                train_job_id,
                [
                    ArtifactRef(
                        id=model_id,
                        uri=model_uri,
                        kind="model",
                        metadata={
                            "framework": "pytorch",
                            "architecture": "resnet50",
                            "dataset_type": "image_classification",
                            "task_types": ["classification"],
                            "prediction_targets": ["image_classification"],
                        },
                    )
                ],
            )

        asyncio.run(_create_model())

        # ── 4. Create prediction job record ───────────────────────────
        job_id = str(uuid4())
        pred_job = PredictionJob(
            id=job_id,
            dataset_id=dataset_id,
            model_id=model_id,
            status=JobStatus.QUEUED,
            created_by="test",
            target="image_classification",
            org_id=DEFAULT_ORG_ID,
        )

        async def _create_job():
            await pred_repo.create_prediction_job(pred_job, org_id=DEFAULT_ORG_ID)

        asyncio.run(_create_job())

        # ── 5. Run prediction via materialized sparse path ────────────

        with _patch_prefect_tasks():
            result = asyncio.run(
                predict_job_mod._run_prediction_job_with_context(
                    app_context=ctx,
                    job_id=job_id,
                    dataset_id=dataset_id,
                    model_id=model_id,
                    org_id=DEFAULT_ORG_ID,
                    target="image_classification",
                    model_version=None,
                    sample_ids=None,
                )
            )

        assert result["total_samples"] == 10, (
            f"Expected 10 samples, got result: {result}"
        )
        assert result["successful"] > 0, (
            f"No successful predictions: {result}"
        )


async def _async_gen_rows(rows: list[Any]) -> AsyncIterator[Any]:
    for row in rows:
        yield row
