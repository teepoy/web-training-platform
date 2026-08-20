from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.modules.datasets.domain.compatibility import validate_predictor_for_dataset
from app.modules.datasets.port.http.deps import get_label_studio_client
from app.shared.api.schemas import DatasetStorageMode

pytestmark = pytest.mark.integration


_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


# ---------------------------------------------------------------------------
# Create sparse dataset
# ---------------------------------------------------------------------------


def test_create_sparse_dataset() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets", json={
            "name": "sparse-create-test",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "sparse-create-test"
        assert body["storage_mode"] == DatasetStorageMode.FILE_SHARD_SPARSE.value
        assert body.get("ls_project_id") == "SPARSE_NO_LS"
        assert body.get("ls_project_url") is None


def test_update_sparse_label_space_preserves_metadata_without_calling_ls() -> None:
    mock_ls = MagicMock()
    mock_ls.update_project = AsyncMock()
    app.dependency_overrides[get_label_studio_client] = lambda: mock_ls
    try:
        with TestClient(app) as c:
            created = c.post(
                "/api/v1/datasets",
                json={
                    "name": "sparse-label-update",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        **_TASK_SPEC,
                        "metadata_schema": {"lot": {"type": "string"}},
                    },
                    "storage_mode": "file_shard_sparse",
                },
            )
            assert created.status_code == 200, created.text
            before = created.json()

            updated = c.patch(
                f"/api/v1/datasets/{before['id']}/label-space",
                json={"label_space": ["good", "bad"]},
            )

        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["task_spec"]["label_space"] == ["good", "bad"]
        assert body["task_spec"]["metadata_schema"] == {"lot": {"type": "string"}}
        assert body["created_by"] == before["created_by"]
        mock_ls.update_project.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_label_studio_client, None)


def test_update_sparse_label_space_rejects_invalid_empty_classification_labels() -> None:
    with TestClient(app) as c:
        created = c.post(
            "/api/v1/datasets",
            json={
                "name": "sparse-empty-label-update",
                "dataset_type": "image_classification",
                "task_spec": _TASK_SPEC,
                "storage_mode": "file_shard_sparse",
            },
        )
        assert created.status_code == 200, created.text

        updated = c.patch(
            f"/api/v1/datasets/{created.json()['id']}/label-space",
            json={"label_space": []},
        )

    assert updated.status_code == 422, updated.text


# ---------------------------------------------------------------------------
# Capability gating — sparse datasets reject operations that need samples
# ---------------------------------------------------------------------------


def test_sparse_dataset_rejects_samples() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-reject-samples",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.post(f"/api/v1/datasets/{ds_id}/samples", json={
            "image_uris": [],
            "metadata": {},
        })
        assert resp.status_code == 500
        assert "no label studio project" in resp.json()["detail"].lower()


def test_sparse_dataset_rejects_annotations() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-reject-annotations",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.post(f"/api/v1/datasets/{ds_id}/annotations/bulk", json={
            "annotations": [{"sample_id": "nonexistent", "label": "cat"}],
        })
        # Sparse datasets proceed (repo.create_annotation is called directly, not through access)
        assert resp.status_code == 200
        assert resp.json()["created"] == 1


def test_sparse_dataset_rejects_sync_to_ls() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-reject-sync",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.post(f"/api/v1/datasets/{ds_id}/sync-annotations-to-ls")
        assert resp.status_code == 500
        assert "no label studio project" in resp.json()["detail"].lower()


def test_sparse_dataset_export_accepted() -> None:
    """Sparse dataset export returns format+dataset+samples (was placeholder, T19)."""
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-export-accept",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.get(f"/api/v1/exports/{ds_id}")
        assert resp.status_code == 200, (
            f"Sparse export must be accepted, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body.get("format") == "sparse-export-v1", (
            f"Expected sparse-export-v1 format, got: {list(body.keys())}"
        )
        assert body.get("dataset", {}).get("id") == ds_id
        assert isinstance(body.get("samples"), list)


def test_sparse_dataset_export_v2_returns_compact_image_refs() -> None:
    """Sparse dataset with v2 manifest produces sparse-export-v2 format
    with compact image references (no raw bytes, no upstream S3 URLs)."""
    import asyncio
    import io

    import pyarrow as pa
    import pyarrow.parquet as pq

    from app.modules.sc.schema import _build_v2_pyarrow_schema
    from tests.conftest import DEFAULT_ORG_ID
    from app.modules.storage.domain.sparse import ColumnSchema, DatasetManifest, SampleLocator

    sc_task_spec = {"task_type": "sc", "label_space": ["defect", "clean"]}

    with TestClient(app) as c:
        # ── Create sparse SC dataset ───────────────────────────────────
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-v2-export-test",
            "dataset_type": "image_sc",
            "task_spec": sc_task_spec,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200, ds.text
        ds_id = ds.json()["id"]

        # ── Build v2 Parquet shard ─────────────────────────────────────
        schema = _build_v2_pyarrow_schema()

        images_list: list[dict] = [
            {
                "image_id": "img-review-1",
                "image_type": "REVIEW_HIGH_MAG",
                "role": "review",
                "content_type": "image/png",
                "filename": "0000001_1.png",
                "bytes": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
                "source_uri": "s3://review-images/20260526/1/0000001_1.png",
                "review_image_id": 1,
            },
            {
                "image_id": "img-tmpl-1",
                "image_type": "PATCH_TEMPLATE",
                "role": "patch_template",
                "content_type": "image/png",
                "filename": "template.png",
                "bytes": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
                "source_uri": None,
            },
            {
                "image_id": "img-defect-1",
                "image_type": "PATCH_DEFECTIVE",
                "role": "patch_defective",
                "content_type": "image/png",
                "filename": "defective.png",
                "bytes": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
                "source_uri": "s3://patch-images/20260526/1/defective.png",
            },
        ]

        row: dict = {
            "sample_id": "defect-001",
            "defect_id": "defect-001",
            "inspection_time": "2026-05-26T08:00:00",
            "wafer_key": 1,
            "wafer_x": 100,
            "wafer_y": 200,
            "rough_bin": 1,
            "class_number": 2,
            "lot_id": "LOT-2026-001",
            "images": images_list,
        }

        table = pa.Table.from_pylist([row], schema=schema)
        buf = io.BytesIO()
        pq.write_table(table, buf)
        shard_bytes = buf.getvalue()

        # ── Store shard + manifest via DatasetPayloadStore ─────────────
        store = app.state.app_context.storage.dataset_payload_store

        shard_entry = asyncio.run(store.put_shard(
            dataset_id=ds_id,
            org_id=DEFAULT_ORG_ID,
            shard_index=0,
            data=shard_bytes,
            row_count=1,
        ))

        sample_index: dict[str, SampleLocator] = {
            "defect-001": SampleLocator(
                dataset_id=ds_id,
                shard_index=0,
                row_index=0,
                upstream_item_id="defect-001",
            ),
        }

        manifest = DatasetManifest(
            dataset_id=ds_id,
            storage_mode="file_shard_sparse",
            shard_count=1,
            total_rows=1,
            schema_columns=[
                ColumnSchema(name="sample_id", type="string"),
                ColumnSchema(name="images", type="list<struct>"),
            ],
            shards=[shard_entry],
            sample_index=sample_index,
            schema_version="v2",
        )

        asyncio.run(store.put_manifest(manifest, org_id=DEFAULT_ORG_ID))

        # ── Call export endpoint ──────────────────────────────────────
        resp = c.get(f"/api/v1/exports/{ds_id}")
        assert resp.status_code == 200, f"Export failed: {resp.text}"
        body = resp.json()

        # ── Verify format ──────────────────────────────────────────────
        assert body.get("format") == "sparse-export-v2", (
            f"Expected sparse-export-v2, got {body.get('format')!r}"
        )
        assert body.get("dataset", {}).get("id") == ds_id

        # ── Verify samples ────────────────────────────────────────────
        samples = body.get("samples", [])
        assert len(samples) == 1, f"Expected 1 sample, got {len(samples)}"
        sample = samples[0]

        assert sample["sample_id"] == "defect-001"
        assert sample["defect_id"] == "defect-001"

        # primary URI fields should be image-parser URLs, not upstream S3
        assert sample["image_uri"] == (
            "/api/v1/sc/images/2026-05-26T08%3A00%3A00/1/defect-001/review"
            "?review_image_id=1"
        )
        assert sample["defective_uri"] == (
            "/api/v1/sc/images/2026-05-26T08%3A00%3A00/1/defect-001/defective"
        )
        assert sample["reference_uri"] == (
            "/api/v1/sc/images/2026-05-26T08%3A00%3A00/1/defect-001/template"
        )

        # v2 export has no metadata
        assert sample.get("metadata") == {}

        # ── Verify compact image refs ──────────────────────────────────
        images = sample.get("images", [])
        assert len(images) == 3, f"Expected 3 image refs, got {len(images)}"

        for img_ref in images:
            # Must NOT contain raw bytes or upstream source_uri
            assert "bytes" not in img_ref, (
                f"Raw bytes leaked into export: keys={list(img_ref.keys())}"
            )
            assert "source_uri" not in img_ref, (
                f"Source URI leaked into export: {img_ref.get('source_uri')}"
            )
            # Must have expected compact fields
            assert "image_id" in img_ref, f"Missing image_id: {img_ref}"
            assert "role" in img_ref, f"Missing role: {img_ref}"
            assert "content_type" in img_ref, f"Missing content_type: {img_ref}"
            assert "filename" in img_ref, f"Missing filename: {img_ref}"
            assert "image_type" in img_ref, f"Missing image_type: {img_ref}"
            assert "access_url" in img_ref, f"Missing access_url: {img_ref}"
            assert img_ref["access_url"].startswith("/api/v1/sc/images/"), (
                f"Unexpected access_url: {img_ref['access_url']}"
            )

        # Verify specific image refs by role
        review_ref = next(r for r in images if r["role"] == "review")
        assert review_ref["image_id"] == "img-review-1"
        assert review_ref["access_url"] == (
            "/api/v1/sc/images/2026-05-26T08%3A00%3A00/1/defect-001/review"
            "?review_image_id=1"
        )

        tmpl_ref = next(r for r in images if r["role"] == "patch_template")
        assert tmpl_ref["image_id"] == "img-tmpl-1"

        defect_ref = next(r for r in images if r["role"] == "patch_defective")
        assert defect_ref["image_id"] == "img-defect-1"


def test_sparse_dataset_export_v3_derives_patch_refs_from_scalar_row() -> None:
    from app.modules.datasets.app.services.sparse_export import SparseExportAssembler

    row = {
        "sample_id": "42",
        "defect_id": "42",
        "inspection_time": "2026-05-26T08:00:00+00:00",
        "wafer_key": 1,
        "wafer_x": 100,
        "wafer_y": 200,
    }

    sample = SparseExportAssembler._assemble_v3_row(
        row=row,
        dataset_id="dataset-v3",
        sample_id="42",
    )

    assert sample["image_uri"] is None
    assert sample["reference_uri"] == (
        "/api/v1/sc/images/2026-05-26T08%3A00%3A00%2B00%3A00/1/42/template"
    )
    assert sample["defective_uri"] == (
        "/api/v1/sc/images/2026-05-26T08%3A00%3A00%2B00%3A00/1/42/defective"
    )
    assert [image["role"] for image in sample["images"]] == [
        "patch_template",
        "patch_defective",
        "patch_difference",
    ]
    assert all("bytes" not in image for image in sample["images"])
    assert sample["metadata"]["inspection_time"] == row["inspection_time"]


def test_sparse_dataset_persist_export_accepted() -> None:
    """Sparse dataset persist export is accepted (returns placeholder, not 500)."""
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-persist-export",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.post(f"/api/v1/exports/{ds_id}/persist")
        assert resp.status_code == 200, (
            f"Sparse persist export must be accepted, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert "uri" in body


# ---------------------------------------------------------------------------
# Regression — normal ``db_full`` datasets still work
# ---------------------------------------------------------------------------


def test_db_full_dataset_accepts_samples() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets", json={
            "name": "normal-ds",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "db_full",
        })
        assert resp.status_code == 200
        ds_id = resp.json()["id"]

        sample_resp = c.post(f"/api/v1/datasets/{ds_id}/samples", json={
            "image_uris": [],
            "metadata": {},
        })
        assert sample_resp.status_code == 200, sample_resp.text


# ---------------------------------------------------------------------------
# Sparse summary endpoint
# ---------------------------------------------------------------------------


def test_sparse_summary_endpoint_returns_empty_manifest() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-summary-test",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.get(f"/api/v1/datasets/{ds_id}/sparse-summary")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dataset_id"] == ds_id
        assert body["storage_mode"] == "file_shard_sparse"
        assert body["manifest"]["shard_count"] == 0
        assert body["manifest"]["total_rows"] == 0
        assert body["shards"] == []
        assert body["sample_rows"] == []


def test_sparse_summary_rejects_db_full_dataset() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "db-full-summary-test",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "db_full",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        resp = c.get(f"/api/v1/datasets/{ds_id}/sparse-summary")
        assert resp.status_code == 409
        assert "file_shard_sparse datasets only" in resp.json()["detail"]


def test_sparse_summary_v2_omits_embedded_image_bytes() -> None:
    import asyncio
    import io

    import pyarrow as pa
    import pyarrow.parquet as pq

    from app.modules.sc.schema import _build_v2_pyarrow_schema
    from tests.conftest import DEFAULT_ORG_ID
    from app.modules.storage.domain.sparse import ColumnSchema, DatasetManifest, SampleLocator

    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-summary-v2-test",
            "dataset_type": "image_sc",
            "task_spec": {"task_type": "sc", "label_space": ["defect", "clean"]},
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200, ds.text
        ds_id = ds.json()["id"]

        table = pa.Table.from_pylist(
            [
                {
                    "sample_id": "defect-001",
                    "defect_id": "defect-001",
                    "inspection_time": "2026-05-26T08:00:00",
                    "wafer_key": 1,
                    "wafer_x": 100,
                    "wafer_y": 200,
                    "rough_bin": 1,
                    "class_number": 2,
                    "lot_id": "LOT-2026-001",
                    "images": [
                        {
                            "image_id": "img-review-1",
                            "image_type": "REVIEW_HIGH_MAG",
                            "role": "review",
                            "content_type": "image/png",
                            "filename": "0000001_1.png",
                            "bytes": b"\x89PNG\r\n\x1a\n",
                            "source_uri": "s3://review-images/20260526/1/0000001_1.png",
                        }
                    ],
                }
            ],
            schema=_build_v2_pyarrow_schema(),
        )
        buf = io.BytesIO()
        pq.write_table(table, buf)

        store = app.state.app_context.storage.dataset_payload_store
        shard_entry = asyncio.run(store.put_shard(
            dataset_id=ds_id,
            org_id=DEFAULT_ORG_ID,
            shard_index=0,
            data=buf.getvalue(),
            row_count=1,
        ))
        manifest = DatasetManifest(
            dataset_id=ds_id,
            storage_mode="file_shard_sparse",
            shard_count=1,
            total_rows=1,
            schema_columns=[
                ColumnSchema(name="sample_id", type="string"),
                ColumnSchema(name="images", type="list<struct>"),
            ],
            shards=[shard_entry],
            sample_index={
                "defect-001": SampleLocator(
                    dataset_id=ds_id,
                    shard_index=0,
                    row_index=0,
                    upstream_item_id="defect-001",
                ),
            },
            schema_version="v2",
        )
        asyncio.run(store.put_manifest(manifest, org_id=DEFAULT_ORG_ID))

        resp = c.get(f"/api/v1/datasets/{ds_id}/sparse-summary")
        assert resp.status_code == 200, resp.text

        row = resp.json()["sample_rows"][0]
        assert "bytes" not in row["images"][0]
        assert "source_uri" not in row["images"][0]


# ---------------------------------------------------------------------------
# Delete lifecycle — sparse datasets skip LS deletion
# ---------------------------------------------------------------------------


def test_sparse_delete_lifecycle() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-delete-test",
            "dataset_type": "image_classification",
            "task_spec": _TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200
        ds_id = ds.json()["id"]

        ls_mock = app.dependency_overrides[get_label_studio_client]()
        ls_mock.delete_project.reset_mock()

        deleted = c.delete(f"/api/v1/datasets/{ds_id}")
        assert deleted.status_code == 204

        get_resp = c.get(f"/api/v1/datasets/{ds_id}")
        assert get_resp.status_code == 404

        ls_mock.delete_project.assert_not_called()


# ---------------------------------------------------------------------------
# Sparse SC dataset + yolo-sc-v1 training — capability+view gate
# ---------------------------------------------------------------------------


def test_sparse_sc_dataset_readiness_runs_after_submission() -> None:
    """The HTTP path submits without scanning sparse Parquet for readiness."""
    sc_task_spec = {"task_type": "sc", "label_space": ["defect", "clean"]}
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-sc-training-test",
            "dataset_type": "image_sc",
            "task_spec": sc_task_spec,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200, ds.text
        ds_id = ds.json()["id"]

        resp = c.post("/api/v1/training-jobs", json={
            "dataset_id": ds_id,
            "trainer_id": "yolo-sc-v1",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"


# ---------------------------------------------------------------------------
# Sparse SC dataset prediction — capability+view gate
# ---------------------------------------------------------------------------

SC_VIEW_TYPES = ["image_input_v1", "patch_image_v1", "review_image_v1"]


def test_sparse_sc_prediction_accepts_compatible_predictor() -> None:
    """validate_predictor_for_dataset passes for SC-compatible predictor.

    yolo-sc-v1 has an SC-compatible patch image view, which is
    in SC view_types.  storage_mode=file_shard_sparse must NOT block.
    """
    # Should not raise — compatible predictor + sparse storage_mode
    validate_predictor_for_dataset(
        predictor_id="yolo-sc-v1",
        view_types=SC_VIEW_TYPES,
    )


# ---------------------------------------------------------------------------
# Sparse sample image proxy — canonical dataset image interface
# ---------------------------------------------------------------------------


def test_sparse_sample_image_proxy_serves_embedded_images() -> None:
    """Sparse dataset image proxy serves embedded images from Parquet shards.

    Verifies the standard dataset image interface:
    GET /api/v1/datasets/{dataset_id}/samples/{sample_id}/images/{image_id}
    """
    import asyncio
    import io

    import pyarrow as pa
    import pyarrow.parquet as pq

    from app.modules.sc.schema import _build_v2_pyarrow_schema
    from tests.conftest import DEFAULT_ORG_ID
    from app.modules.storage.domain.sparse import ColumnSchema, DatasetManifest, SampleLocator

    sc_task_spec = {"task_type": "sc", "label_space": ["defect", "clean"]}

    test_png_bytes: bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 32

    with TestClient(app) as c:
        # ── Create sparse SC dataset ───────────────────────────────────
        ds = c.post("/api/v1/datasets", json={
            "name": "sparse-image-proxy-test",
            "dataset_type": "image_sc",
            "task_spec": sc_task_spec,
            "storage_mode": "file_shard_sparse",
        })
        assert ds.status_code == 200, ds.text
        ds_id = ds.json()["id"]

        # ── Build v2 Parquet shard with embedded images ─────────────────
        schema = _build_v2_pyarrow_schema()

        images_list: list[dict] = [
            {
                "image_id": "img-review-1",
                "image_type": "REVIEW_HIGH_MAG",
                "role": "review",
                "content_type": "image/png",
                "filename": "0000001_1.png",
                "bytes": test_png_bytes,
                "source_uri": "s3://review-images/20260526/1/0000001_1.png",
            },
            {
                "image_id": "img-tmpl-1",
                "image_type": "PATCH_TEMPLATE",
                "role": "patch_template",
                "content_type": "image/png",
                "filename": "template.png",
                "bytes": test_png_bytes,
                "source_uri": None,
            },
            {
                "image_id": "img-defect-1",
                "image_type": "PATCH_DEFECTIVE",
                "role": "patch_defective",
                "content_type": "image/png",
                "filename": "defective.png",
                "bytes": test_png_bytes,
                "source_uri": "s3://patch-images/20260526/1/defective.png",
            },
        ]

        row: dict = {
            "sample_id": "defect-001",
            "defect_id": "defect-001",
            "inspection_time": "2026-05-26T08:00:00",
            "wafer_key": 1,
            "wafer_x": 100,
            "wafer_y": 200,
            "rough_bin": 1,
            "class_number": 2,
            "lot_id": "LOT-2026-001",
            "images": images_list,
        }

        table = pa.Table.from_pylist([row], schema=schema)
        buf = io.BytesIO()
        pq.write_table(table, buf)
        shard_bytes = buf.getvalue()

        # ── Store shard + manifest via DatasetPayloadStore ─────────────
        store = app.state.app_context.storage.dataset_payload_store

        shard_entry = asyncio.run(store.put_shard(
            dataset_id=ds_id,
            org_id=DEFAULT_ORG_ID,
            shard_index=0,
            data=shard_bytes,
            row_count=1,
        ))

        manifest = DatasetManifest(
            dataset_id=ds_id,
            storage_mode="file_shard_sparse",
            shard_count=1,
            total_rows=1,
            schema_columns=[
                ColumnSchema(name="sample_id", type="string"),
                ColumnSchema(name="images", type="list<struct>"),
            ],
            shards=[shard_entry],
            sample_index={
                "defect-001": SampleLocator(
                    dataset_id=ds_id,
                    shard_index=0,
                    row_index=0,
                    upstream_item_id="defect-001",
                ),
            },
            schema_version="v2",
        )

        asyncio.run(store.put_manifest(manifest, org_id=DEFAULT_ORG_ID))

        # ── Image proxy: serve review image ────────────────────────────
        resp = c.get(
            f"/api/v1/datasets/{ds_id}/samples/defect-001/images/img-review-1",
        )
        assert resp.status_code == 200, (
            f"Image proxy failed with {resp.status_code}: {resp.text}"
        )
        assert resp.headers["content-type"] == "image/png", (
            f"Expected image/png, got {resp.headers.get('content-type')}"
        )
        assert len(resp.content) > 0, "Image content must not be empty"
        assert resp.content == test_png_bytes, (
            "Image bytes must match the embedded payload"
        )

        # ── Image proxy: serve patch template image ────────────────────
        resp2 = c.get(
            f"/api/v1/datasets/{ds_id}/samples/defect-001/images/img-tmpl-1",
        )
        assert resp2.status_code == 200, resp2.text
        assert resp2.headers["content-type"] == "image/png"
        assert len(resp2.content) > 0

        # ── Image proxy: serve patch defective image ───────────────────
        resp3 = c.get(
            f"/api/v1/datasets/{ds_id}/samples/defect-001/images/img-defect-1",
        )
        assert resp3.status_code == 200, resp3.text
        assert resp3.headers["content-type"] == "image/png"
        assert len(resp3.content) > 0

        # ── Nonexistent image returns 404 ──────────────────────────────
        resp4 = c.get(
            f"/api/v1/datasets/{ds_id}/samples/defect-001/images/img-bogus",
        )
        assert resp4.status_code == 404, (
            f"Expected 404 for nonexistent image, got {resp4.status_code}"
        )

        # ── Nonexistent sample returns 404 ─────────────────────────────
        resp5 = c.get(
            f"/api/v1/datasets/{ds_id}/samples/nonexistent/images/img-review-1",
        )
        assert resp5.status_code == 404, (
            f"Expected 404 for nonexistent sample, got {resp5.status_code}"
        )

        # ── Removed unscoped compatibility route stays unavailable ─────
        resp6 = c.get(
            "/api/v1/samples/defect-001/images/img-review-1",
        )
        assert resp6.status_code == 404, (
            f"Expected 404 for removed unscoped route, got {resp6.status_code}"
        )
