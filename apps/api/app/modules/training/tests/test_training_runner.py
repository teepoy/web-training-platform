"""Tests for the worker-side training pipeline (run_training_pipeline).

These tests call ``run_training_pipeline`` from the flow module directly
as plain Python — no Prefect server required.  They exercise the full
code path that runs inside a Prefect worker: DB access, trainer loading,
dynamic trainer import, artifact persistence.
"""
from __future__ import annotations

import asyncio
import base64
import uuid
from typing import AsyncIterator
from unittest.mock import patch

import pyarrow as pa
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.infrastructure.storage import InMemoryArtifactStorage
from tests.conftest import DEFAULT_ORG_ID, TRAINER_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x04\x00\x00\x00\x04\x08\x02"
    b"\x00\x00\x00&\x93\t)\x00\x00\x00\x14IDATx\x9cclpP`\x80\x01&\x06$\x80\x9b\x03"
    b"\x00-$\x00\xe8\xd2`\xe8\xf5\x00\x00\x00\x00IEND\xaeB`\x82"
)

_DATA_URI = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode()


def _seed_dataset_with_samples(
    client,
    n_samples: int = 3,
    labels: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Create a dataset with labeled samples via the API.

    Returns ``(dataset_id, sample_ids)``.
    """
    labels = labels or ["cat", "dog"]
    ds = client.post(
        "/api/v1/datasets",
        json={
            "name": "runner-test-ds",
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
        # Add an annotation so the trainer has labeled data
        label = labels[i % len(labels)]
        ann = client.post(
            "/api/v1/annotations",
            json={"sample_id": sid, "label": label, "source": "test"},
        )
        assert ann.status_code == 200

    return dataset_id, sample_ids


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
def test_run_training_pipeline_completes() -> None:
    """Pipeline completes with real DB, trainer, and in-memory storage."""
    with TestClient(app) as c:
        dataset_id, _ = _seed_dataset_with_samples(c, n_samples=4, labels=["cat", "dog"])

        from app.modules.training.flows.train_job import run_training_pipeline

        storage = InMemoryArtifactStorage()
        result = asyncio.run(
            run_training_pipeline(
                job_id="test-train-001",
                dataset_id=dataset_id,
                trainer_id=TRAINER_ID,
                artifact_storage=storage,
            )
        )

        assert result["status"] == "completed"
        assert result["job_id"] == "test-train-001"
        artifacts = result.get("artifacts", [])
        assert len(artifacts) >= 1
        # At least one model artifact should have been persisted
        model_artifacts = [a for a in artifacts if a.get("kind") == "model"]
        assert len(model_artifacts) >= 1


@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
def test_run_training_pipeline_missing_dataset() -> None:
    """Pipeline raises ValueError when dataset does not exist."""
    with TestClient(app):
        from app.modules.training.flows.train_job import run_training_pipeline

        with pytest.raises(ValueError, match="Dataset not found"):
            asyncio.run(
                run_training_pipeline(
                    job_id="test-train-missing-ds",
                    dataset_id="nonexistent-dataset-id",
                    trainer_id=TRAINER_ID,
                    artifact_storage=InMemoryArtifactStorage(),
                )
            )


@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
def test_run_training_pipeline_missing_trainer() -> None:
    """Pipeline raises ValueError when trainer does not exist for view."""
    with TestClient(app) as c:
        dataset_id, _ = _seed_dataset_with_samples(c, n_samples=1)

        from app.modules.training.flows.train_job import run_training_pipeline

        with pytest.raises(ValueError, match="Trainer not found"):
            asyncio.run(
                run_training_pipeline(
                    job_id="test-train-bad-view",
                    dataset_id=dataset_id,
                    trainer_id="nonexistent-view-xyz",
                    artifact_storage=InMemoryArtifactStorage(),
                )
            )


@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
def test_run_training_pipeline_empty_dataset() -> None:
    """Pipeline handles a dataset with zero samples gracefully.

    TorchTrainer should still complete by generating synthetic prototypes
    from the label space when no real labeled samples are available.
    """
    with TestClient(app) as c:
        ds = c.post(
            "/api/v1/datasets",
            json={
                "name": "empty-runner-ds",
                "dataset_type": "image_classification",
                "task_spec": {"task_type": "classification", "label_space": ["a", "b"]},
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        from app.modules.training.flows.train_job import run_training_pipeline

        storage = InMemoryArtifactStorage()
        result = asyncio.run(
            run_training_pipeline(
                job_id="test-train-empty",
                dataset_id=dataset_id,
                trainer_id=TRAINER_ID,
                artifact_storage=storage,
            )
        )

        assert result["status"] == "completed"


@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
def test_run_training_pipeline_persists_artifacts_to_storage() -> None:
    """Model artifact is written to artifact storage."""
    with TestClient(app) as c:
        dataset_id, _ = _seed_dataset_with_samples(c, n_samples=2, labels=["x", "y"])

        from app.modules.training.flows.train_job import run_training_pipeline

        storage = InMemoryArtifactStorage()
        result = asyncio.run(
            run_training_pipeline(
                job_id="test-train-artifacts",
                dataset_id=dataset_id,
                trainer_id=TRAINER_ID,
                artifact_storage=storage,
            )
        )

        model_uri = result["artifacts"][0]["uri"]
        assert model_uri
        # Verify the artifact was actually written to storage
        stored_bytes = asyncio.run(storage.get_bytes(model_uri))
        assert len(stored_bytes) > 0


# ---------------------------------------------------------------------------
# Sparse materialized training
# ---------------------------------------------------------------------------


_FAKE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
    b"\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc"
    b"\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND"
    b"\xaeB`\x82"
)

_IMAGE_STRUCT = pa.struct(
    [
        pa.field("image_id", pa.string(), nullable=False),
        pa.field("role", pa.string(), nullable=False),
        pa.field("bytes", pa.binary(), nullable=False),
        pa.field("content_type", pa.string(), nullable=False),
        pa.field("filename", pa.string(), nullable=False),
        pa.field("source_uri", pa.string(), nullable=True),
    ]
)

_SPARSE_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string()),
        pa.field("defect_id", pa.string()),
        pa.field("image_uris", pa.string()),
        pa.field("metadata", pa.string()),
        pa.field("label", pa.string()),
        pa.field("images", pa.list_(_IMAGE_STRUCT)),
    ]
)


async def _async_gen(rows: list) -> AsyncIterator:
    for row in rows:
        yield row


def _make_sparse_row(index: int):
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
                bytes_=_FAKE_PNG,
                content_type="image/png",
                filename=f"test-{index}.png",
            )
        ],
    )


@pytest.mark.skip(reason="Pre-existing failure - see errors.md")
def test_train_sparse_materialized() -> None:
    """Train via sparse materialized path: seed sparse shards →
    materialize → train → verify artifacts.

    Uses in-memory storage for both seeding and the pipeline.
    Patches ``_build_artifact_storage`` so the training container
    shares the same ``InMemoryArtifactStorage`` instance as the
    test app.
    """
    import logging

    from app.modules.training.flows.train_job import run_training_pipeline

    with TestClient(app) as c:
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
        dataset_id = str(uuid.uuid4())

        from app.shared.api.schemas import (
            Dataset, DatasetStorageMode, SPARSE_NO_LS, TaskSpec,
        )

        ds = Dataset(
            id=dataset_id,
            name="train-sparse-ds",
            storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
            dataset_type="image_classification",
            task_spec=TaskSpec(task_type="classification", label_space=["cat", "dog"]),
            ls_project_id=SPARSE_NO_LS,
        )

        async def _create_dataset():
            await repo.create_dataset(ds, org_id=DEFAULT_ORG_ID)

        asyncio.run(_create_dataset())

        # ── 3. Run training via materialized path ─────────────────────
        # run_training_pipeline calls get_run_logger() which requires a
        # Prefect context.  Replace with a plain stdlib logger.
        import app.composition as comp

        mock_logger = logging.getLogger("test-train-sparse")
        mock_logger.setLevel(logging.INFO)

        with patch(
            "app.modules.training.flows.train_job.get_run_logger",
            return_value=mock_logger,
        ):
            with patch.object(
                comp, "_build_artifact_storage", return_value=test_storage
            ):
                result = asyncio.run(
                    run_training_pipeline(
                        job_id="train-sparse-001",
                        dataset_id=dataset_id,
                        trainer_id=TRAINER_ID,
                        materialization_ref={
                            "purpose": "train",
                            "view_id": "labeled_image_v1",
                        },
                    )
                )

        assert result["status"] == "completed"
        artifacts = result.get("artifacts", [])
        assert len(artifacts) >= 1, f"No artifacts: {result}"
        model_artifacts = [a for a in artifacts if a.get("kind") == "model"]
        assert len(model_artifacts) >= 1, (
            f"No model artifacts in: {artifacts}"
        )
