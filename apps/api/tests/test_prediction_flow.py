"""Tests for the worker-side prediction flow (run_prediction_job and chunk tasks).

These tests call the prediction flow functions directly as plain Python —
no Prefect server required.  They exercise the full code path that runs
inside a Prefect worker: Container wiring, DB access, sample iteration,
inference worker delegation, prediction persistence.

Note: The chunk tasks in predict_job.py create their own ``Container()``
instances.  In test mode these get separate in-memory storage, so we
patch the Container import to return the app's main container (which
has the seeded data and mocked services).
"""
from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient

from app.domain.models import ArtifactRef, PredictionJob
from app.domain.types import JobStatus
from app.main import app, container as app_container
from tests.conftest import DEFAULT_ORG_ID, PRESET_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x04\x00\x00\x00\x04\x08\x02"
    b"\x00\x00\x00&\x93\t)\x00\x00\x00\x14IDATx\x9cclpP`\x80\x01&\x06$\x80\x9b\x03"
    b"\x00-$\x00\xe8\xd2`\xe8\xf5\x00\x00\x00\x00IEND\xaeB`\x82"
)

_DATA_URI = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode()


def _use_app_container():
    """Patch predict_job.Container to return the app's main container.

    This ensures the flow tasks share the same DB, storage, and mocked
    services as the test setup.  We also patch the @task-decorated
    functions to call their underlying .fn directly, bypassing Prefect's
    task engine which would otherwise create a new execution context.
    """
    import app.flows.predict_job as _mod

    return _multi_patch(
        patch.object(_mod, "Container", return_value=app_container),
        patch.object(_mod, "predict_chunk", side_effect=_mod.predict_chunk.fn),
        patch.object(_mod, "embed_chunk", side_effect=_mod.embed_chunk.fn),
        patch.object(_mod, "persist_chunk_results", side_effect=_mod.persist_chunk_results.fn),
    )


class _multi_patch:
    """Context manager that applies multiple patches together."""

    def __init__(self, *patches):
        self._patches = patches
        self._mocks = []

    def __enter__(self):
        self._mocks = [p.__enter__() for p in self._patches]
        return self._mocks

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.__exit__(*exc)


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
            json={"sample_id": sid, "label": label, "source": "test"},
        )
        assert ann.status_code == 200

    # Create a training job record (needed for model→job FK)
    job_resp = client.post(
        "/api/v1/training-jobs",
        json={"dataset_id": dataset_id, "preset_id": PRESET_ID, "created_by": "test"},
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

    repo = app_container.repository()
    storage = app_container.artifact_storage()

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
    asyncio.run(app_container.repository().create_prediction_job(job, org_id=DEFAULT_ORG_ID))
    return job.id


# ---------------------------------------------------------------------------
# Tests — run_prediction_job
# ---------------------------------------------------------------------------


def test_run_prediction_job_classification() -> None:
    """Full classification prediction flow completes and persists results."""
    with TestClient(app) as c:
        dataset_id, model_id, sample_ids = _seed_prediction_setup(c, n_samples=3)
        job_id = _create_prediction_job_record(dataset_id, model_id)

        from app.flows.predict_job import run_prediction_job

        with _use_app_container():
            result = asyncio.run(
                run_prediction_job(
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


def test_run_prediction_job_with_sample_subset() -> None:
    """Prediction flow processes only the specified sample_ids."""
    with TestClient(app) as c:
        dataset_id, model_id, sample_ids = _seed_prediction_setup(c, n_samples=4)
        subset = sample_ids[:2]
        job_id = _create_prediction_job_record(dataset_id, model_id)

        from app.flows.predict_job import run_prediction_job

        with _use_app_container():
            result = asyncio.run(
                run_prediction_job(
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


def test_run_prediction_job_missing_dataset() -> None:
    """Flow raises ValueError for nonexistent dataset."""
    with TestClient(app):
        from app.flows.predict_job import run_prediction_job

        with _use_app_container():
            with pytest.raises(ValueError, match="Dataset not found"):
                asyncio.run(
                    run_prediction_job(
                        job_id="pred-missing-ds",
                        dataset_id="nonexistent-dataset",
                        model_id="nonexistent-model",
                        org_id=DEFAULT_ORG_ID,
                        target="image_classification",
                        model_version=None,
                        sample_ids=None,
                    )
                )


def test_run_prediction_job_embedding_target() -> None:
    """Embedding target path completes without error."""
    with TestClient(app) as c:
        dataset_id, model_id, sample_ids = _seed_prediction_setup(c, n_samples=2)
        job_id = _create_prediction_job_record(dataset_id, model_id)

        from app.flows.predict_job import run_prediction_job

        with _use_app_container():
            result = asyncio.run(
                run_prediction_job(
                    job_id=job_id,
                    dataset_id=dataset_id,
                    model_id=model_id,
                    org_id=DEFAULT_ORG_ID,
                    target="embedding",
                    model_version=None,
                    sample_ids=None,
                )
            )

        assert result["total_samples"] == 2
        assert "completed_at" in result


# ---------------------------------------------------------------------------
# Tests — individual chunk tasks
# ---------------------------------------------------------------------------


def test_predict_chunk_missing_model() -> None:
    """predict_chunk raises ValueError when model does not exist."""
    with TestClient(app):
        from app.flows.predict_job import predict_chunk

        with pytest.raises(ValueError, match="Model not found"):
            asyncio.run(
                predict_chunk.fn(
                    model_id="nonexistent-model",
                    org_id=DEFAULT_ORG_ID,
                    target="image_classification",
                    prompt=None,
                    sample_ids=["sample-1"],
                )
            )


def test_predict_chunk_empty_samples() -> None:
    """predict_chunk returns empty list when no sample IDs resolve."""
    with TestClient(app) as c:
        dataset_id, model_id, _ = _seed_prediction_setup(c, n_samples=1)

        from app.flows.predict_job import predict_chunk

        result = asyncio.run(
            predict_chunk.fn(
                model_id=model_id,
                org_id=DEFAULT_ORG_ID,
                target="image_classification",
                prompt=None,
                sample_ids=["nonexistent-sample-id"],
            )
        )

        assert result == []


def test_persist_chunk_results_writes_predictions() -> None:
    """persist_chunk_results creates prediction records and events in DB."""
    with TestClient(app) as c:
        dataset_id, model_id, sample_ids = _seed_prediction_setup(c, n_samples=2)
        job_id = _create_prediction_job_record(dataset_id, model_id)

        worker_results = [
            {"sample_id": sid, "label": "cat", "confidence": 0.95, "scores": {"cat": 0.95, "dog": 0.05}}
            for sid in sample_ids
        ]

        from app.flows.predict_job import persist_chunk_results

        result = asyncio.run(
            persist_chunk_results.fn(
                job_id=job_id,
                model_id=model_id,
                org_id=DEFAULT_ORG_ID,
                target="image_classification",
                model_version="test-v1",
                sample_ids=sample_ids,
                worker_results=worker_results,
            )
        )

        assert result["successful"] == 2
        assert result["failed"] == 0
        assert len(result["predictions"]) == 2


# ---------------------------------------------------------------------------
# Tests — GPU worker invocation (isolated mocks, Task 14)
# ---------------------------------------------------------------------------


def _isolated_gpu_worker_patch(app_container):
    """Override GPU and inference worker with fresh mocks for one test.

    Returns ``(mock_gpu, mock_inference, cleanup)`` where ``cleanup`` is a
    zero-arg callable that resets both overrides.
    """
    mock_gpu = MagicMock()
    mock_gpu.predict_batch = AsyncMock(
        side_effect=lambda **kwargs: [
            {"sample_id": s["sample_id"], "label": "cat", "confidence": 0.9}
            for s in kwargs.get("samples", [])
        ]
    )
    mock_gpu.embed_batch = AsyncMock(
        side_effect=lambda **kwargs: [
            {"sample_id": s["sample_id"], "embedding": [0.1, 0.2]}
            for s in kwargs.get("samples", [])
        ]
    )
    mock_inference = MagicMock()
    mock_inference.predict_batch = AsyncMock(return_value=[])
    mock_inference.embed_batch = AsyncMock(return_value=[])

    app_container.gpu_worker.override(providers.Object(mock_gpu))
    app_container.inference_worker.override(providers.Object(mock_inference))

    def _cleanup() -> None:
        app_container.gpu_worker.reset_override()
        app_container.inference_worker.reset_override()

    return mock_gpu, mock_inference, _cleanup


def test_predict_chunk_calls_gpu_worker_predict_batch() -> None:
    """predict_chunk invokes GPU worker predict_batch, NOT inference worker."""
    with TestClient(app) as c:
        dataset_id, model_id, sample_ids = _seed_prediction_setup(c, n_samples=3)
        from app.main import container as _app_container
        from app.flows.predict_job import predict_chunk

        mock_gpu, mock_inference, cleanup = _isolated_gpu_worker_patch(_app_container)
        try:
            with _use_app_container():
                worker_results = asyncio.run(
                    predict_chunk.fn(
                        model_id=model_id,
                        org_id=DEFAULT_ORG_ID,
                        target="image_classification",
                        prompt=None,
                        sample_ids=sample_ids,
                    )
                )

            assert isinstance(worker_results, list)
            assert len(worker_results) == 3
            mock_gpu.predict_batch.assert_awaited_once()
            mock_inference.predict_batch.assert_not_awaited()
            # Verify call arguments
            call_kwargs = mock_gpu.predict_batch.call_args.kwargs
            assert call_kwargs["model_id"] == model_id
            assert call_kwargs["target"] == "image_classification"
            assert len(call_kwargs["samples"]) == 3
        finally:
            cleanup()


def test_embed_chunk_calls_gpu_worker_embed_batch() -> None:
    """embed_chunk invokes GPU worker embed_batch, NOT inference worker."""
    with TestClient(app) as c:
        dataset_id, model_id, sample_ids = _seed_prediction_setup(c, n_samples=3)
        from app.main import container as _app_container
        from app.flows.predict_job import embed_chunk

        mock_gpu, mock_inference, cleanup = _isolated_gpu_worker_patch(_app_container)
        try:
            with _use_app_container():
                chunk_summary = asyncio.run(
                    embed_chunk.fn(
                        dataset_id=dataset_id,
                        org_id=DEFAULT_ORG_ID,
                        embed_model="test-embed-model",
                        force=False,
                        sample_ids=sample_ids,
                    )
                )

            assert isinstance(chunk_summary, dict)
            assert chunk_summary.get("embedding_model") == "test-embed-model"
            mock_gpu.embed_batch.assert_awaited_once()
            mock_inference.embed_batch.assert_not_awaited()
            # Verify call arguments
            call_kwargs = mock_gpu.embed_batch.call_args.kwargs
            assert call_kwargs["model_name"] == "test-embed-model"
            assert len(call_kwargs["samples"]) == 3
        finally:
            cleanup()


def test_run_prediction_job_prefers_gpu_worker_over_inference() -> None:
    """run_prediction_job uses GPU worker even when inference worker is also configured."""
    with TestClient(app) as c:
        dataset_id, model_id, sample_ids = _seed_prediction_setup(c, n_samples=4)
        job_id = _create_prediction_job_record(dataset_id, model_id)
        from app.main import container as _app_container
        from app.flows.predict_job import run_prediction_job

        mock_gpu, mock_inference, cleanup = _isolated_gpu_worker_patch(_app_container)
        try:
            with _use_app_container():
                result = asyncio.run(
                    run_prediction_job(
                        job_id=job_id,
                        dataset_id=dataset_id,
                        model_id=model_id,
                        org_id=DEFAULT_ORG_ID,
                        target="image_classification",
                        model_version=None,
                        sample_ids=None,
                    )
                )

            assert result["total_samples"] == 4
            mock_gpu.predict_batch.assert_awaited_once()
            mock_inference.predict_batch.assert_not_awaited()
        finally:
            cleanup()
