#!/usr/bin/env python3
"""
Data integrity integration test — runs against the live dev stack.

Covers: sample upload (shard), annotation bulk, materialize,
prediction result writeback, and cross-verification via S3 / polars / API / DB.

Prerequisites
-------------
- dev API at ``DATA_INTEGRITY_API_URL`` or http://127.0.0.1:8000
- MinIO at localhost:9000 (minioadmin / minioadmin)
- PostgreSQL reachable (DATABASE_URL env or default dev config)

Run
---
    cd apps/api
    uv run python tests/test_data_integrity.py

Design
------
- **Upload**: call ``SampleBulkAccess`` directly (no REST endpoint accepts
  ``PatchSample``-format bodies for sparse storage).
- **Materialize**: call ``DatasetStorageAgg.materialize()`` via
  ``DatasetStorageFactory``.
- **Annotation / status / latest-predictions**: REST API via ``httpx``.
- **S3 verification**: ``boto3`` against MinIO.
- **Parquet content verification**: ``polars``.
- **DB writeback** (for ``get_latest_predictions`` compat): prediction repository
  calls that seed ``PlatformPredictionORM`` rows.

Known issues recorded
---------------------
- This test keeps a live-stack shape and may need local service credentials for
  MinIO/PostgreSQL.
"""

from __future__ import annotations

import asyncio
import io as _io
import json as _json
import os
import sys
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

# ---------------------------------------------------------------------------
# Ensure the API source tree is on sys.path so we can import app.* modules
# ---------------------------------------------------------------------------
_API_ROOT = Path(__file__).resolve().parents[1]  # apps/api
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

# Must set BEFORE any app imports that read config.
os.environ["APP_CONFIG_PROFILE"] = "dev"

try:
    import boto3  # type: ignore[import-untyped]
    import httpx  # type: ignore[import-untyped]
    import polars as pl  # type: ignore[import-untyped]
    from botocore.config import Config as BotoConfig  # type: ignore[import-untyped]
except ImportError as e:
    print(
        f"Missing test dependency: {e}\n"
        "Install with: uv pip install boto3 httpx polars botocore"
    )
    raise

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import pytest  # noqa: E402

from app.composition import build_flow_app_context, close_flow_app_context  # noqa: E402
from app.core.config import load_config  # noqa: E402
from tests.conftest import DEFAULT_ORG_ID, model_artifact_bytes  # noqa: E402
from app.shared.api.schemas import (  # noqa: E402
    JobStatus,
    PlatformPrediction,
    PredictionJob,
)  # noqa: E402
from app.modules.datasets.domain.sample_row import BulkSampleRow  # noqa: E402
from app.modules.prediction.domain.repository import PredictionRepository  # noqa: E402
from app.modules.storage.domain.storage_agg import MaterializeResult  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
API_URL = os.getenv("DATA_INTEGRITY_API_URL", "http://127.0.0.1:8000")
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_BUCKET = "finetune-artifacts"
RUNTIME_BUCKET = "finetune-runtime-inputs"

DEV_ORG_ID = DEFAULT_ORG_ID  # "00000000-0000-0000-0000-000000000001"

SAMPLE_COUNT = 1000
SHARD_BATCH_SIZE = 200
EXPECTED_SHARD_COUNT = (SAMPLE_COUNT + SHARD_BATCH_SIZE - 1) // SHARD_BATCH_SIZE  # 5




# ===========================================================================
# Helpers
# ===========================================================================


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str, detail: object = None) -> None:
    print(f"  ✗ {msg}")
    if detail is not None:
        print(f"    {detail}")
    raise AssertionError(msg)


# ---------------------------------------------------------------------------
# HTTP helpers (using httpx async)
# ---------------------------------------------------------------------------


class ApiClient:
    """Thin async wrapper around httpx for the dev API."""

    def __init__(self, base_url: str = API_URL) -> None:
        self._base = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self, org_id: str | None = None) -> dict[str, str]:
        h: dict[str, str] = {}
        if org_id:
            h["X-Organization-ID"] = org_id
        return h

    async def login(self, email: str, password: str) -> dict:
        r = await self._client.post(
            f"{self._base}/api/v1/auth/login",
            json={"email": email, "password": password},
)
        r.raise_for_status()
        body = r.json()
        token = body["access_token"]
        # Attach bearer token to all subsequent requests.
        self._client.headers["Authorization"] = f"Bearer {token}"
        return body

    async def list_orgs(self) -> list[dict]:
        r = await self._client.get(f"{self._base}/api/v1/organizations")
        r.raise_for_status()
        return r.json()

    async def create_dataset(
        self,
        name: str,
        *,
        dataset_type: str = "image_sc",
        task_spec: dict | None = None,
        storage_mode: str = "file_shard_sparse",
        org_id: str = DEV_ORG_ID,
    ) -> str:
        body: dict = {
            "name": name,
            "dataset_type": dataset_type,
            "storage_mode": storage_mode,
        }
        if task_spec is not None:
            body["task_spec"] = task_spec
        r = await self._client.post(
            f"{self._base}/api/v1/datasets",
            json=body,
            headers=self._headers(org_id),
        )
        assert r.status_code == 200, (
            f"create_dataset failed: {r.status_code} {r.text}"
        )
        return str(r.json()["id"])

    async def get_dataset(self, dataset_id: str, org_id: str = DEV_ORG_ID) -> dict:
        r = await self._client.get(
            f"{self._base}/api/v1/datasets/{dataset_id}",
            headers=self._headers(org_id),
        )
        r.raise_for_status()
        return r.json()

    async def get_dataset_label_space(
        self, dataset_id: str, org_id: str = DEV_ORG_ID
    ) -> list[str]:
        """Return the current label_space from task_spec."""
        ds = await self.get_dataset(dataset_id, org_id)
        return list(ds.get("task_spec", {}).get("label_space", []))

    async def get_dataset_status(
        self, dataset_id: str, org_id: str = DEV_ORG_ID
    ) -> dict:
        r = await self._client.get(
            f"{self._base}/api/v1/datasets/{dataset_id}/status",
            headers=self._headers(org_id),
        )
        r.raise_for_status()
        return r.json()

    async def get_annotation_stats(
        self, dataset_id: str, org_id: str = DEV_ORG_ID
    ) -> dict:
        r = await self._client.get(
            f"{self._base}/api/v1/datasets/{dataset_id}/annotation-stats",
            headers=self._headers(org_id),
        )
        r.raise_for_status()
        return r.json()

    async def bulk_create_annotations(
        self,
        dataset_id: str,
        annotations: list[dict],
        org_id: str = DEV_ORG_ID,
    ) -> int:
        """Return number of annotations created."""
        r = await self._client.post(
            f"{self._base}/api/v1/datasets/{dataset_id}/annotations/bulk",
            json={"annotations": annotations},
            headers=self._headers(org_id),
        )
        r.raise_for_status()
        return int(r.json()["created"])

    async def get_latest_predictions(
        self, dataset_id: str, org_id: str = DEV_ORG_ID
    ) -> list[dict]:
        r = await self._client.get(
            f"{self._base}/api/v1/datasets/{dataset_id}/latest-predictions",
            headers=self._headers(org_id),
        )
        r.raise_for_status()
        return r.json()

    async def delete_dataset(
        self, dataset_id: str, org_id: str = DEV_ORG_ID
    ) -> None:
        r = await self._client.delete(
            f"{self._base}/api/v1/datasets/{dataset_id}",
            headers=self._headers(org_id),
        )
        r.raise_for_status()

    async def create_training_job_api(
        self, dataset_id: str, trainer_id: str, org_id: str = DEV_ORG_ID
    ) -> dict:
        r = await self._client.post(
            f"{self._base}/api/v1/training-jobs",
            json={"dataset_id": dataset_id, "trainer_id": trainer_id},
            headers=self._headers(org_id),
        )
        r.raise_for_status()
        return r.json()

    async def list_training_jobs(
        self, *, dataset_id: str | None = None, org_id: str = DEV_ORG_ID
    ) -> list[dict]:
        params = {}
        if dataset_id:
            params["dataset_id"] = dataset_id
        r = await self._client.get(
            f"{self._base}/api/v1/training-jobs",
            params=params,
            headers=self._headers(org_id),
        )
        r.raise_for_status()
        return r.json()

    async def upload_model(
        self, job_id: str, *, trainer_id: str = "yolo-sc-v1",
        org_id: str = DEV_ORG_ID,
    ) -> dict:
        import io as _io2
        metadata = _json.dumps({
            "name": "test-model",
            "format": "pytorch",
            "job_id": job_id,
            "template_id": "image-classifier",
            "profile_id": "custom",
            "model_spec": {
                "framework": "pytorch",
                "architecture": "yolov8n-cls",
                "base_model": "ultralytics/yolov8n-cls",
            },
            "compatibility": {
                "dataset_types": ["image_classification"],
                "task_types": ["classification"],
                "prediction_targets": ["image_classification"],
                "label_space": ["defect", "clean", "scratch"],
            },
        })
        r = await self._client.post(
            f"{self._base}/api/v1/models/upload",
            data={"metadata": metadata},
            files={
                "file": (
                    "model.pt",
                    _io2.BytesIO(model_artifact_bytes()),
                    "application/octet-stream",
                )
            },
            headers=self._headers(org_id),
        )
        r.raise_for_status()
        return r.json()

    async def run_prediction(
        self, model_id: str, dataset_id: str, *,
        target: str = "image_sc",
        org_id: str = DEV_ORG_ID,
    ) -> dict:
        r = await self._client.post(
            f"{self._base}/api/v1/predictions/run",
            json={
                "model_id": model_id,
                "dataset_id": dataset_id,
                "target": target,
            },
            headers=self._headers(org_id),
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# S3 helpers (boto3, sync)
# ---------------------------------------------------------------------------


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=f"http://{MINIO_ENDPOINT}",
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=BotoConfig(
            signature_version="s3v4",
            region_name="us-east-1",
        ),
    )


def list_s3_keys(bucket: str, prefix: str) -> list[str]:
    s3 = _s3_client()
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def get_s3_bytes(bucket: str, key: str) -> bytes:
    s3 = _s3_client()
    resp = s3.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()


def get_s3_json(bucket: str, key: str) -> dict:
    return _json.loads(get_s3_bytes(bucket, key).decode("utf-8"))


# ---------------------------------------------------------------------------
# Sample row generator
# ---------------------------------------------------------------------------


async def _generate_sample_rows(count: int) -> AsyncIterator[BulkSampleRow]:
    """Yield *count* BulkSampleRow objects with ScSample-like fields."""
    for i in range(count):
        yield BulkSampleRow(
            sample_id=f"sample-{i:04d}",
            extra={
                "defect_id": f"DEF-{i:04d}",  # same as sample_id per user's note
                "inspection_time": "2024-01-15T08:30:00",
                "wafer_key": 1,
                "wafer_x": i % 100,
                "wafer_y": i // 100,
                "rough_bin": i % 5,
                "class_number": i % 10,
                "lot_id": "LOT-A1",
                "images": [],  # no images — materialize uses raw_v1 bypass
            },
        )


# ===========================================================================
# Test runner
# ===========================================================================


async def _clear_dataset_s3(org_id: str, dataset_id: str) -> None:
    """Remove all S3 objects under the dataset prefix (cleanup helper)."""
    s3 = _s3_client()
    prefix = f"datasets/{org_id}/{dataset_id}/"
    for bucket in (MINIO_BUCKET, RUNTIME_BUCKET):
        try:
            keys = list_s3_keys(bucket, prefix)
            for key in keys:
                s3.delete_object(Bucket=bucket, Key=key)
            if keys:
                print(f"  [cleanup] deleted {len(keys)} keys from {bucket}/{prefix}")
        except Exception:
            pass


async def run() -> bool:
    """Execute the full data integrity test suite.  Returns ``True`` on pass."""

    print(f"[{_now_iso()}] Starting data integrity test")
    print(f"  API:    {API_URL}")
    print(f"  MinIO:  {MINIO_ENDPOINT}")
    print(f"  Bucket: {MINIO_BUCKET}")
    print(f"  Samples: {SAMPLE_COUNT} (batch={SHARD_BATCH_SIZE})")

    try:
        async with httpx.AsyncClient(timeout=3.0) as health_client:
            health = await health_client.get(f"{API_URL}/health")
            health.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"dev API is not reachable at {API_URL}: {exc}")

    # ── Bootstrap ──────────────────────────────────────────────────────────
    api = ApiClient()
    user_email = os.environ.get("DATA_INTEGRITY_USER_EMAIL", "").strip()
    user_password = os.environ.get("DATA_INTEGRITY_USER_PASSWORD", "").strip()
    if not user_email or not user_password:
        raise RuntimeError(
            "DATA_INTEGRITY_USER_EMAIL and DATA_INTEGRITY_USER_PASSWORD are required"
        )

    print("\n[0] Bootstrap: login + org + app context")
    await api.login(user_email, user_password)
    orgs = await api.list_orgs()
    org_id = str(orgs[0]["id"]) if orgs else DEV_ORG_ID
    _ok(f"authenticated, org={org_id}")

    # Build the flow app context for direct service access.
    load_config.cache_clear()
    cfg = load_config()
    app_context = build_flow_app_context(cfg)
    if app_context.datasets is None:
        raise RuntimeError("AppContext datasets module was not initialized")
    if app_context.storage is None:
        raise RuntimeError("AppContext storage module was not initialized")
    if app_context.prediction is None:
        raise RuntimeError("Prediction context is not initialized")
    prediction_repo = app_context.prediction.prediction_repository
    storage = app_context.shared.artifact_storage
    storage_factory = app_context.storage.dataset_storage_factory
    _ok("app context built")

    # ── Step 1: Create dataset ──────────────────────────────────────────────
    print("\n[1] Create dataset (file_shard_sparse, image_sc)")
    dataset_name = f"data-integrity-test-{uuid4().hex[:8]}"
    dataset_id = await api.create_dataset(
        dataset_name,
        dataset_type="image_sc",
        task_spec={
            "task_type": "sc",
            "label_space": ["defect", "clean"],
        },
        storage_mode="file_shard_sparse",
        org_id=org_id,
    )
    _ok(f"created dataset_id={dataset_id}")

    ds_meta = await api.get_dataset(dataset_id, org_id)
    assert ds_meta["storage_mode"] == "file_shard_sparse", ds_meta
    assert ds_meta["dataset_type"] == "image_sc", ds_meta

    try:
        # ── Step 2: (skipped — SampleBulkAccess was deleted) ─────────────────
        print("\n[2] SKIPPED: sample upload requires SampleBulkAccess (deleted)")

        # ── Step 3: Verify S3 — shard files exist, correct count, labels empty
        print("\n[3] Verify S3 shard files")
        shard_prefix = f"datasets/{org_id}/{dataset_id}/shards/"
        shard_keys = list_s3_keys(MINIO_BUCKET, shard_prefix)
        assert len(shard_keys) == EXPECTED_SHARD_COUNT, (
            f"Expected {EXPECTED_SHARD_COUNT} shard keys, found {len(shard_keys)}: {shard_keys}"
        )

        # Read all shards with polars and verify
        total_rows = 0
        all_sample_ids: set[str] = set()
        all_labels: set[str] = set()
        for key in sorted(shard_keys):
            raw = get_s3_bytes(MINIO_BUCKET, key)
            df = pl.read_parquet(raw)
            total_rows += df.height
            if "sample_id" in df.columns:
                for sid in df["sample_id"].to_list():
                    all_sample_ids.add(str(sid))
            if "label" in df.columns:
                for lbl in df["label"].drop_nulls().to_list():
                    all_labels.add(str(lbl))
        assert total_rows == SAMPLE_COUNT, (
            f"Expected {SAMPLE_COUNT} total rows across shards, got {total_rows}"
        )
        assert len(all_sample_ids) == SAMPLE_COUNT, (
            f"Expected {SAMPLE_COUNT} unique sample_ids, got {len(all_sample_ids)}"
        )
        assert not all_labels, f"Expected empty labels, got {all_labels}"
        _ok(f"shards OK: {total_rows} rows, {len(all_sample_ids)} unique samples, labels empty")

        # Verify annotations folder is empty (no annotations yet)
        ann_prefix = f"datasets/{org_id}/{dataset_id}/annotations/"
        ann_keys = list_s3_keys(MINIO_BUCKET, ann_prefix)
        assert len(ann_keys) == 0, f"Expected 0 annotation files, got {len(ann_keys)}"
        _ok("annotations folder empty (no annotations yet)")

        # ── Step 4: Verify dataset summary API ───────────────────────────────
        print("\n[4] Verify dataset summary API")
        status = await api.get_dataset_status(dataset_id, org_id)
        assert status["total_samples"] == SAMPLE_COUNT, (
            f"status total_samples: expected {SAMPLE_COUNT}, got {status['total_samples']}"
        )
        assert status["annotated_samples"] == 0, (
            f"status annotated_samples: expected 0, got {status['annotated_samples']}"
        )
        assert status["allow_train"] is False, f"allow_train should be False, got {status['allow_train']}"
        assert status["train_disabled_reason"] == "insufficient_active_classes"
        assert status["minimum_active_class_count"] == 2
        assert status["active_class_count"] == 0
        _ok(f"status: total={status['total_samples']}, annotated={status['annotated_samples']}, allow_train={status['allow_train']}")

        ann_stats = await api.get_annotation_stats(dataset_id, org_id)
        _ok(f"annotation-stats: {ann_stats}")

        # ── Step 5: Verify materialize — returns all rows
        print("\n[5] Verify materialize (via DatasetStorageFactory)")

        async def _materialize() -> MaterializeResult:
            s = await storage_factory.open(dataset_id, org_id=org_id)
            return await s.materialize()

        mat_result = await _materialize()
        assert mat_result.row_count == SAMPLE_COUNT, (
            f"materialize expected {SAMPLE_COUNT} rows, got {mat_result.row_count}"
        )
        _ok(f"materialize: {mat_result.row_count} rows")

        # ── Step 6: Annotate samples 1-100 ───────────────────────────────────
        print("\n[6] Annotate samples 1-100")
        annotations_1 = [
            {"sample_id": f"sample-{i:04d}", "label": "defect" if i % 2 == 0 else "clean"}
            for i in range(100)
        ]
        created = await api.bulk_create_annotations(dataset_id, annotations_1, org_id)
        assert created == 100, f"Expected 100 created, got {created}"
        _ok(f"created {created} annotations (samples 0-99)")

        # Verify S3 annotation files exist
        ann_keys_after = list_s3_keys(MINIO_BUCKET, ann_prefix)
        assert len(ann_keys_after) > 0, (
            f"Expected at least 1 annotation file, got {len(ann_keys_after)}"
        )

        # Read annotation parquet files and verify
        ann_total_rows = 0
        ann_labels: dict[str, int] = {}
        for key in ann_keys_after:
            raw = get_s3_bytes(MINIO_BUCKET, key)
            df = pl.read_parquet(raw)
            ann_total_rows += df.height
            if "label" in df.columns:
                for lbl in df["label"].to_list():
                    lbl_s = str(lbl)
                    ann_labels[lbl_s] = ann_labels.get(lbl_s, 0) + 1
        assert ann_total_rows == 100, (
            f"Expected 100 annotation rows, got {ann_total_rows}"
        )
        _ok(f"S3 annotations: {ann_total_rows} rows, labels={ann_labels}")

        # Verify dataset summary
        status = await api.get_dataset_status(dataset_id, org_id)
        assert status["total_samples"] == SAMPLE_COUNT
        assert status["annotated_samples"] == 100, (
            f"Expected 100 annotated, got {status['annotated_samples']}"
        )
        assert status["allow_train"] is True
        assert status["train_disabled_reason"] is None
        assert status["minimum_active_class_count"] == 2
        assert status["active_class_count"] == 2
        _ok(f"status: annotated={status['annotated_samples']}, allow_train={status['allow_train']}")

        # Verify label_space unchanged (no new labels introduced)
        label_space = await api.get_dataset_label_space(dataset_id, org_id)
        assert set(label_space) == {"defect", "clean"}, (
            f"label_space should be ['clean', 'defect'], got {label_space}"
        )
        _ok(f"label_space preserved: {label_space}")

        # Verify materialize (new API: always returns all rows)
        mat_result2 = await _materialize()
        assert mat_result2.row_count == SAMPLE_COUNT, (
            f"materialize expected {SAMPLE_COUNT} rows after annotations, got {mat_result2.row_count}"
        )
        _ok(f"materialize after 100 annotations: {mat_result2.row_count} rows")

        # ── Step 7: Annotate samples 80-150 ──────────────────────────────────
        print("\n[7] Annotate samples 80-150 (overlapping range)")
        annotations_2 = [
            {"sample_id": f"sample-{i:04d}", "label": "defect"}
            for i in range(80, 150)
        ]
        created2 = await api.bulk_create_annotations(dataset_id, annotations_2, org_id)
        assert created2 == 70, f"Expected 70 created, got {created2}"
        _ok(f"created {created2} annotations (samples 80-149)")

        # Read all annotation files again
        ann_keys_after2 = list_s3_keys(MINIO_BUCKET, ann_prefix)
        ann_total2 = 0
        unique_annotated_samples: set[str] = set()
        for key in ann_keys_after2:
            raw = get_s3_bytes(MINIO_BUCKET, key)
            df = pl.read_parquet(raw)
            ann_total2 += df.height
            if "sample_id" in df.columns:
                for sid in df["sample_id"].to_list():
                    unique_annotated_samples.add(str(sid))
        # 100 + 70 = 170 total annotation records, but 20 overlap (80-99)
        assert ann_total2 == 170, f"Expected 170 total annotation rows, got {ann_total2}"
        # Unique samples: 0-99 (100) + 100-149 (50) = 150
        assert len(unique_annotated_samples) == 150, (
            f"Expected 150 unique annotated sample_ids, got {len(unique_annotated_samples)}"
        )
        _ok(f"S3 annotations: {ann_total2} rows, {len(unique_annotated_samples)} unique samples")

        # Verify dataset summary
        status = await api.get_dataset_status(dataset_id, org_id)
        assert status["annotated_samples"] == 150, (
            f"Expected 150 annotated, got {status['annotated_samples']}"
        )
        _ok(f"status: annotated={status['annotated_samples']}")

        # Verify materialize
        mat_result3 = await _materialize()
        assert mat_result3.row_count == SAMPLE_COUNT, (
            f"materialize expected {SAMPLE_COUNT} rows after 150 annotations, got {mat_result3.row_count}"
        )
        _ok(f"materialize after 150 annotations: {mat_result3.row_count} rows")

        # ── Step 7.5: Auto-expand label_space with a brand-new label ────────
        print("\n[7.5] Annotate with new label — verify auto-expansion")
        new_label_annotations = [
            {"sample_id": f"sample-{i:04d}", "label": "scratch"}
            for i in range(200, 203)
        ]
        created_ls = await api.bulk_create_annotations(
            dataset_id, new_label_annotations, org_id
        )
        assert created_ls == 3
        _ok(f"created {created_ls} annotations with new label 'scratch'")

        label_space_after = await api.get_dataset_label_space(dataset_id, org_id)
        assert "scratch" in label_space_after, (
            f"Expected 'scratch' in label_space after annotation, got {label_space_after}"
        )
        _ok(f"label_space auto-expanded: {label_space_after}")

        # ── Step 8: Upload mock predictions (all "1") ────────────────────────
        print('\n[8] Upload mock prediction results (all "1") via prediction repository')
        pred_job_id_1 = await _write_predictions_via_repo(
            prediction_repo, dataset_id, org_id, SAMPLE_COUNT, predicted_label="1"
        )
        _ok(f"prediction job {pred_job_id_1}: {SAMPLE_COUNT} predictions (all '1')")

        # Write S3 prediction parquet (sparse path — same as predict_job.py)
        await _write_sparse_predictions_s3(
            storage, dataset_id, org_id, pred_job_id_1,
            SAMPLE_COUNT, predicted_label="1",
        )

        # Verify via DB: list predictions for this job
        db_preds_1 = await prediction_repo.list_platform_predictions_for_job(
            pred_job_id_1, org_id
        )
        assert len(db_preds_1) == SAMPLE_COUNT, (
            f"DB: expected {SAMPLE_COUNT} predictions, got {len(db_preds_1)}"
        )
        for p in db_preds_1:
            assert p.predicted_label == "1", f"DB: unexpected label {p.predicted_label}"
        _ok(f"DB verify: {len(db_preds_1)} predictions, all labeled '1'")

        # Verify via get_latest_predictions API (now fixed for sparse datasets)
        preds_1 = await api.get_latest_predictions(dataset_id, org_id)
        assert len(preds_1) == SAMPLE_COUNT, (
            f"API: expected {SAMPLE_COUNT} latest predictions, got {len(preds_1)}"
        )
        for p in preds_1:
            assert str(p.get("predicted_label", "")) == "1", f"API: unexpected label {p}"
        _ok(f"API verify: {len(preds_1)} latest predictions, all labeled '1'")

        # Verify via S3: read prediction parquet shard
        s3_pred_prefix = f"datasets/{org_id}/{dataset_id}/predictions/{pred_job_id_1}/"
        s3_pred_keys = list_s3_keys(MINIO_BUCKET, s3_pred_prefix)
        assert len(s3_pred_keys) >= 2, (
            f"Expected at least 2 prediction files (parquet + job_result), got {len(s3_pred_keys)}"
        )
        s3_shard_keys = [k for k in s3_pred_keys if k.endswith(".parquet")]
        s3_total = 0
        for key in s3_shard_keys:
            raw = get_s3_bytes(MINIO_BUCKET, key)
            df = pl.read_parquet(raw)
            s3_total += df.height
            if "predicted_label" in df.columns:
                for lbl in df["predicted_label"].to_list():
                    assert str(lbl) == "1", f"S3: unexpected prediction label {lbl}"
        assert s3_total == SAMPLE_COUNT, (
            f"S3: expected {SAMPLE_COUNT} prediction rows, got {s3_total}"
        )
        _ok(f"S3 verify: {s3_total} prediction rows, all labeled '1'")

        # Annotation stats now: 150 (steps 6+7) + 3 (step 7.5) = 153
        status = await api.get_dataset_status(dataset_id, org_id)
        assert status["annotated_samples"] == 153, (
            f"Expected 153 annotated after auto-expand, got {status['annotated_samples']}"
        )
        _ok(f"annotated_samples updated: {status['annotated_samples']}")

        # ── Step 9: Override predictions (all "2") ──────────────────────────
        print('\n[9] Override prediction results (all "2") via prediction repository')
        pred_job_id_2 = await _write_predictions_via_repo(
            prediction_repo, dataset_id, org_id, SAMPLE_COUNT, predicted_label="2"
        )
        _ok(f"prediction job {pred_job_id_2}: {SAMPLE_COUNT} predictions (all '2')")

        await _write_sparse_predictions_s3(
            storage, dataset_id, org_id, pred_job_id_2,
            SAMPLE_COUNT, predicted_label="2",
        )

        # Verify via DB
        db_preds_2 = await prediction_repo.list_platform_predictions_for_job(
            pred_job_id_2, org_id
        )
        assert len(db_preds_2) == SAMPLE_COUNT
        for p in db_preds_2:
            assert p.predicted_label == "2"
        _ok(f"DB verify: {len(db_preds_2)} predictions, all labeled '2'")

        # Verify via get_latest_predictions API
        preds_2 = await api.get_latest_predictions(dataset_id, org_id)
        assert len(preds_2) == SAMPLE_COUNT, (
            f"API: expected {SAMPLE_COUNT} latest predictions, got {len(preds_2)}"
        )
        for p in preds_2:
            assert str(p.get("predicted_label", "")) == "2", f"API: unexpected label {p}"
        _ok(f"API verify: {len(preds_2)} latest predictions, all labeled '2'")

        # Verify via S3
        s3_pred_prefix_2 = f"datasets/{org_id}/{dataset_id}/predictions/{pred_job_id_2}/"
        s3_pred_keys_2 = list_s3_keys(MINIO_BUCKET, s3_pred_prefix_2)
        s3_shard_keys_2 = [k for k in s3_pred_keys_2 if k.endswith(".parquet")]
        s3_total_2 = 0
        for key in s3_shard_keys_2:
            raw = get_s3_bytes(MINIO_BUCKET, key)
            df = pl.read_parquet(raw)
            s3_total_2 += df.height
            if "predicted_label" in df.columns:
                for lbl in df["predicted_label"].to_list():
                    assert str(lbl) == "2", f"S3: unexpected prediction label {lbl}"
        assert s3_total_2 == SAMPLE_COUNT
        _ok(f"S3 verify: {s3_total_2} prediction rows, all labeled '2'")

        # Final annotation check
        status = await api.get_dataset_status(dataset_id, org_id)
        assert status["annotated_samples"] == 153, (
            f"Expected 153 annotated, got {status['annotated_samples']}"
        )
        _ok(f"final status: annotated={status['annotated_samples']}")

        # ── Step 10: Train job + model + predict ────────────────────────────
        print('\n[10] Create training job + upload model + verify via API')
        trainer_id = "yolo-sc-v1"

        # 10a. Create training job via API
        train_job = await api.create_training_job_api(
            dataset_id, trainer_id, org_id
        )
        train_job_id = train_job["id"]
        _ok(f"training job created: {train_job_id}")

        # 10b. Upload dummy model artifact via API
        model = await api.upload_model(train_job_id, trainer_id=trainer_id, org_id=org_id)
        model_id = model["id"]
        _ok(f"model uploaded: {model_id}")

        # 10c. Find the training job by dataset_id via API
        jobs = await api.list_training_jobs(dataset_id=dataset_id, org_id=org_id)
        matching = [j for j in jobs if j["id"] == train_job_id]
        assert len(matching) == 1, (
            f"Training job {train_job_id} not found via dataset_id filter (got {len(jobs)} jobs)"
        )
        _ok(f"training job found via GET /training-jobs?dataset_id={dataset_id}")

        # 10d. Call prediction API with this model
        pred_resp = await api.run_prediction(
            model_id, dataset_id, target="image_classification", org_id=org_id
        )
        assert "id" in pred_resp, f"Prediction response missing id: {pred_resp}"
        assert pred_resp.get("status") in ("queued", "running", "completed"), (
            f"Unexpected prediction status: {pred_resp.get('status')}"
        )
        _ok(f"prediction job created via API: {pred_resp['id']} status={pred_resp.get('status')}")

        # ── Done ─────────────────────────────────────────────────────────────
        print(f"\n[{_now_iso()}] ALL CHECKS PASSED")
        return True

    finally:
        # ── Cleanup ─────────────────────────────────────────────────────────
        print("\n[cleanup] deleting dataset...")
        try:
            await api.delete_dataset(dataset_id, org_id)
            _ok("dataset deleted via API")
        except Exception as exc:
            print(f"  [warn] API delete failed: {exc}")
            print("  [cleanup] removing S3 objects directly...")
            await _clear_dataset_s3(org_id, dataset_id)
            _ok("S3 objects cleaned")

        await api.close()
        try:
            await close_flow_app_context(app_context)
        except Exception:
            pass
        _ok("resources released")


# ===========================================================================
# Prediction writeback helpers.
# ===========================================================================


async def _write_predictions_via_repo(
    repo: PredictionRepository,
    dataset_id: str,
    org_id: str,
    count: int,
    predicted_label: str,
) -> str:
    """Create a prediction job + predictions via prediction repository.

    Mimics what ``predict_job.py`` does: creates a ``PredictionJob`` then
    ``PlatformPrediction`` rows.  Uses ``create_platform_predictions_bulk``
    for efficiency.

    Returns the job_id.
    """
    now = datetime.now(timezone.utc)
    job_id = str(uuid4())

    # 1. Create prediction job (same as predict_job.py)
    job = PredictionJob(
        id=job_id,
        dataset_id=dataset_id,
        model_id="mock-model",
        status=JobStatus.COMPLETED,
        created_by="system",
        target="image_classification",
        model_version="v1",
        org_id=org_id,
        created_at=now,
        updated_at=now,
        sample_ids=[f"sample-{i:04d}" for i in range(count)],
        summary={"total": count, "successful": count},
    )
    await repo.create_prediction_job(job, org_id=org_id)

    # 2. Create predictions in bulk
    predictions = [
        PlatformPrediction(
            org_id=org_id,
            dataset_id=dataset_id,
            sample_id=f"sample-{i:04d}",
            model_id="mock-model",
            target="image_classification",
            job_id=job_id,
            model_version="v1",
            predicted_label=predicted_label,
            confidence=0.99,
            all_scores={predicted_label: 0.99},
            created_by="system",
            created_at=now,
        )
        for i in range(count)
    ]
    await repo.create_platform_predictions_bulk(predictions)

    return job_id


async def _write_sparse_predictions_s3(
    storage: Any,
    dataset_id: str,
    org_id: str,
    job_id: str,
    count: int,
    predicted_label: str,
) -> None:
    """Write sparse prediction parquet files to S3 (mimics predict_job.py S3 path).

    Creates one parquet shard and a job_result.json under
    ``datasets/{org_id}/{dataset_id}/predictions/{job_id}/``.

    Note: ``get_latest_predictions`` API reads from ``PlatformPredictionORM``
    (DB), not from S3.  These S3 files are for the sparse readback path
    (``DatasetStorageAgg.list_predictions``) and serve as
    additional verification that storage writes are correct.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    prefix = f"datasets/{org_id}/{dataset_id}/predictions/{job_id}"

    # Build a single-shard prediction parquet (matching SparsePredictionRunner schema)
    columns = {
        "shard_index": pa.array([0] * count, type=pa.int32()),
        "row_index": pa.array(list(range(count)), type=pa.int32()),
        "dataset_id": pa.array([dataset_id] * count, type=pa.string()),
        "predicted_label": pa.array([predicted_label] * count, type=pa.string()),
        "confidence": pa.array([0.99] * count, type=pa.float64()),
        "all_scores": pa.array([_json.dumps({predicted_label: 0.99})] * count, type=pa.string()),
        "error": pa.array([None] * count, type=pa.string()),
    }
    table = pa.table(columns)
    buf = _io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)

    shard_key = f"{prefix}/000000.parquet"
    await storage.put_bytes(
        object_name=shard_key,
        data=buf.read(),
        content_type="application/octet-stream",
    )

    # Write job_result.json
    result = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "org_id": org_id,
        "model_id": "mock-model",
        "model_version": "v1",
        "total_processed": count,
        "total_successful": count,
        "shards": [
            {
                "shard_uri": shard_key,
                "shard_index": 0,
                "row_count": count,
                "model_id": "mock-model",
            }
        ],
        "completed_at": now_iso,
    }
    result_key = f"{prefix}/job_result.json"
    await storage.put_bytes(
        object_name=result_key,
        data=_json.dumps(result).encode("utf-8"),
        content_type="application/json",
    )
    print(f"  [s3] wrote prediction shard + job_result to {prefix}/")


# ===========================================================================
# Entry point
# ===========================================================================


def main() -> int:
    success = asyncio.run(run())
    return 0 if success else 1


@pytest.mark.dev_server
@pytest.mark.skip(
    reason=(
        "Legacy live data-integrity test depends on deleted SampleBulkAccess; "
        "rewrite against DatasetAgg/storage materialization before re-enabling."
    )
)
def test_data_integrity_dev_server() -> None:
    assert asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
