"""RED / specification tests for API sparse prediction readback.

Tests that the API prediction readback endpoint (GET /prediction-jobs/{id}/predictions)
can successfully read worker-produced sparse prediction output when it is in the
canonical format (Parquet shards + job_result.json manifest).

When the worker still writes JSON shards + result.json, the readback returns an
empty list because job_result.json is not found — the endpoint is effectively
unreachable for worker-produced output.  This test sets up a canonical fixture
and verifies the API readback path works end-to-end.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from app.main import app
from app.shared.db.models.auth import OrganizationORM
from app.shared.db.models.datasets import DatasetORM
from app.shared.db.models.prediction import PredictionJobORM

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


def _build_parquet_shard_bytes(
    *,
    rows: list[dict],
) -> bytes:
    """Build a Parquet shard with the canonical prediction column schema."""
    table = pa.table(
        {
            "sample_id": pa.array(
                [r["sample_id"] for r in rows],
                type=pa.string(),
            ),
            "predicted_label": pa.array(
                [r.get("predicted_label", "") for r in rows], type=pa.string()
            ),
            "confidence": pa.array(
                [r.get("confidence") for r in rows], type=pa.float64()
            ),
            "all_scores": pa.array(
                [json.dumps(r.get("all_scores")) if r.get("all_scores") else None for r in rows],
                type=pa.string(),
            ),
            "error": pa.array(
                [r.get("error") for r in rows], type=pa.string()
            ),
        }
    )
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


def _build_job_result_json(
    *,
    job_id: str,
    dataset_id: str,
    model_id: str,
    shard_uris: list[str],
    shard_row_counts: list[int],
    total_processed: int,
    total_successful: int,
) -> bytes:
    """Build a canonical job_result.json manifest."""
    manifest: dict = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "model_id": model_id,
        "model_version": "v1",
        "total_processed": total_processed,
        "total_successful": total_successful,
        "created_at": datetime.now(UTC).isoformat(),
        "shards": [
            {
                "shard_uri": uri,
                "shard_index": i,
                "row_count": count,
                "model_id": model_id,
                "model_version": "v1",
            }
            for i, (uri, count) in enumerate(zip(shard_uris, shard_row_counts))
        ],
    }
    return json.dumps(manifest, indent=2).encode("utf-8")


def test_sparse_readback_missing_job_result_returns_empty():
    """readback returns [] when job_result.json is missing (e.g. worker
    still writes result.json)."""
    with TestClient(app) as c:
        resp = c.get("/api/v1/prediction-jobs/nonexistent-job/predictions")
        assert resp.status_code == 404


def test_sparse_readback_canonical_fixture():
    """Feed the API readback a canonical-format fixture (Parquet shards +
    job_result.json) and assert predictions are returned with expected fields.

    This is a specification test: the fixture mimics what the worker
    SHOULD produce after normalization.  If this passes, the readback
    code is ready for the worker to converge.
    """
    org_id = DEFAULT_ORG_ID
    dataset_id = str(uuid4())
    model_id = str(uuid4())
    job_id = str(uuid4())

    shard_uris = [
        f"memory://datasets/{org_id}/{dataset_id}/predictions/{job_id}/000000.parquet"
    ]
    shard_row_counts = [2]

    prediction_rows = [
        {
            "sample_id": "sample-1",
            "predicted_label": "cat",
            "confidence": 0.95,
            "all_scores": {"cat": 0.95, "dog": 0.05},
            "error": None,
        },
        {
            "sample_id": "sample-2",
            "predicted_label": "dog",
            "confidence": 0.87,
            "all_scores": {"cat": 0.13, "dog": 0.87},
            "error": None,
        },
    ]

    parquet_bytes = _build_parquet_shard_bytes(rows=prediction_rows)
    job_result_bytes = _build_job_result_json(
        job_id=job_id,
        dataset_id=dataset_id,
        model_id=model_id,
        shard_uris=shard_uris,
        shard_row_counts=shard_row_counts,
        total_processed=2,
        total_successful=2,
    )
    with TestClient(app) as c:
        # ── Seed DB ────────────────────────────────────────────────────
        api = app.state.app_context
        async def _seed():
            async with api.shared.session_factory() as session:
                existing = await session.get(OrganizationORM, org_id)
                if not existing:
                    session.add(
                        OrganizationORM(
                            id=org_id,
                            name="Default",
                            slug="default",
                            created_at=datetime.now(UTC),
                        )
                    )
                session.add(
                    DatasetORM(
                        id=dataset_id,
                        org_id=org_id,
                        name="test-sparse-dataset",
                        dataset_type="image_classification",
                        view_types=["image_classification"],
                        dataset_meta={
                            "task_type": "classification",
                            "label_space": ["cat", "dog"],
                        },
                        is_public=False,
                        created_at=datetime.now(UTC),
                        ls_project_id="ls-1",
                        storage_mode="file_shard_sparse",
                    )
                )
                session.add(
                    PredictionJobORM(
                        id=job_id,
                        org_id=org_id,
                        dataset_id=dataset_id,
                        model_id=model_id,
                        status="completed",
                        target="image_classification",
                        model_version="v1",
                        created_by="test-user",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                        summary_json={},
                    )
                )
                await session.commit()

        import asyncio
        asyncio.run(_seed())

        # ── Populate storage ───────────────────────────────────────────
        storage = api.shared.artifact_storage

        async def _populate_storage():
            # Parquet shard
            await storage.put_bytes(
                object_name=(
                    f"datasets/{org_id}/{dataset_id}"
                    f"/predictions/{job_id}/000000.parquet"
                ),
                data=parquet_bytes,
                content_type="application/octet-stream",
            )
            # job_result.json manifest
            await storage.put_bytes(
                object_name=(
                    f"datasets/{org_id}/{dataset_id}"
                    f"/predictions/{job_id}/job_result.json"
                ),
                data=job_result_bytes,
                content_type="application/json",
            )
        asyncio.run(_populate_storage())

        # ── Readback ───────────────────────────────────────────────────
        resp = c.get(
            f"/api/v1/prediction-jobs/{job_id}/predictions",
            params={"offset": 0, "limit": 10},
        )
        assert resp.status_code == 200, f"Readback failed: {resp.text}"

        preds = resp.json()
        assert isinstance(preds, list), f"Expected list, got {type(preds)}"
        assert len(preds) == 2, f"Expected 2 predictions, got {len(preds)}: {preds}"

        # Assert expected columns in each prediction result
        for i, pred in enumerate(preds):
            assert "sample_id" in pred, f"Prediction {i} missing sample_id: {pred}"
            assert "predicted_label" in pred, f"Prediction {i} missing predicted_label: {pred}"
            assert "confidence" in pred, f"Prediction {i} missing confidence: {pred}"
            assert pred["predicted_label"] in ("cat", "dog"), (
                f"Unexpected label: {pred['predicted_label']}"
            )
            if i == 0:
                assert pred["predicted_label"] == "cat"
                assert pred["confidence"] == 0.95
            else:
                assert pred["predicted_label"] == "dog"
                assert pred["confidence"] == 0.87


def test_sparse_readback_legacy_result_json_not_accepted():
    """RED: readback should NOT accept result.json as canonical manifest.

    When only result.json exists (legacy worker format), the readback
    endpoint should return an empty list because job_result.json is the
    canonical contract.
    """
    org_id = DEFAULT_ORG_ID
    dataset_id = str(uuid4())
    model_id = str(uuid4())
    job_id = str(uuid4())

    legacy_manifest = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "model_id": model_id,
        "model_version": "v1",
        "total_processed": 0,
        "total_successful": 0,
        "created_at": datetime.now(UTC).isoformat(),
        "shards": [],
    }

    with TestClient(app) as c:
        api = app.state.app_context

        async def _seed():
            async with api.shared.session_factory() as session:
                existing = await session.get(OrganizationORM, org_id)
                if not existing:
                    session.add(
                        OrganizationORM(
                            id=org_id, name="Default", slug="default",
                            created_at=datetime.now(UTC),
                        )
                    )
                session.add(
                    DatasetORM(
                        id=dataset_id, org_id=org_id,
                        name="test-legacy-dataset",
                        dataset_type="image_classification",
                        view_types=["image_classification"],
                        dataset_meta={
                            "task_type": "classification",
                            "label_space": ["cat", "dog"],
                        },
                        is_public=False, created_at=datetime.now(UTC),
                        ls_project_id="ls-1",
                        storage_mode="file_shard_sparse",
                    )
                )
                session.add(
                    PredictionJobORM(
                        id=job_id, org_id=org_id,
                        dataset_id=dataset_id, model_id=model_id,
                        status="completed", target="image_classification",
                        model_version="v1", created_by="test-user",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                        summary_json={},
                    )
                )
                await session.commit()

        import asyncio
        asyncio.run(_seed())

        # Write ONLY result.json (legacy worker format)
        async def _populate():
            await api.shared.artifact_storage.put_bytes(
                object_name=(
                    f"datasets/{org_id}/{dataset_id}"
                    f"/predictions/{job_id}/result.json"
                ),
                data=json.dumps(legacy_manifest, indent=2).encode("utf-8"),
                content_type="application/json",
            )

        asyncio.run(_populate())

        resp = c.get(
            f"/api/v1/prediction-jobs/{job_id}/predictions",
            params={"offset": 0, "limit": 10},
        )
        assert resp.status_code == 200, f"Readback failed: {resp.text}"

        preds = resp.json()
        # RED: if readback returns predictions from result.json,
        # a legacy fallback was added — that violates the spec.
        assert len(preds) == 0, (
            f"RED: readback accepted legacy result.json instead of requiring "
            f"job_result.json.  Got {len(preds)} predictions.  "
            f"Do NOT add a legacy fallback path."
        )
