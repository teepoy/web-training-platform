"""Integration tests for SC annotation bulk endpoint."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import DEFAULT_ORG_ID
from app.modules.storage.domain.sparse import DatasetManifest, SampleLocator

_SC_TASK_SPEC = {
    "task_type": "sc",
    "label_space": ["defect", "clean"],
}


def _create_sparse_sc_dataset(client: TestClient, name: str) -> str:
    """Create a file_shard_sparse SC dataset via REST (no samples, no LS)."""
    resp = client.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "dataset_type": "image_sc",
            "task_spec": _SC_TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        },
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["id"])


def _seed_sc_sparse_manifest(
    dataset_id: str,
    defect_ids: list[str],
    *,
    sample_ids_by_defect: dict[str, str] | None = None,
) -> None:
    """Write a DatasetManifest with sample_index into the app artifact storage.

    The manifest is placed at the canonical key so that
    the sparse storage aggregate finds it during bulk annotation mapping.
    """
    payload_store = app.state.app_context.storage.dataset_payload_store

    sample_index: dict[str, SampleLocator] = {}
    for i, did in enumerate(defect_ids):
        sample_id = (sample_ids_by_defect or {}).get(did, did)
        sample_index[sample_id] = SampleLocator(
            dataset_id=dataset_id,
            shard_index=0,
            row_index=i,
            upstream_item_id=did,
        )

    manifest = DatasetManifest(
        dataset_id=dataset_id,
        storage_mode="file_shard_sparse",
        shard_count=1,
        total_rows=len(defect_ids),
        sample_index=sample_index,
    )

    asyncio.run(payload_store.put_manifest(manifest, org_id=DEFAULT_ORG_ID))


# ── Sparse bulk annotation integration tests ─────────────────────────


def test_bulk_create_annotations_success():
    """Bulk-create annotations for sparse dataset via manifest sample_index."""
    with TestClient(app) as client:
        dataset_id = _create_sparse_sc_dataset(client, "SC Bulk Sparse")
        _seed_sc_sparse_manifest(dataset_id, ["D001", "D002", "D003"])

        resp = client.post(
            f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
            json={
                "annotations": [
                    {"defect_id": "D001", "label": "scratch", "annotator": "user1"},
                    {"defect_id": "D002", "label": "clean", "annotator": "user2"},
                    {"defect_id": "D003", "label": "crack", "annotator": "user3"},
                ],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["created"] == 3
        storage = app.state.app_context.shared.artifact_storage
        prefix = f"datasets/{DEFAULT_ORG_ID}/{dataset_id}/annotations/"
        annotation_sidecars = asyncio.run(storage.list_prefix(prefix))
        assert len(annotation_sidecars) == 1


def test_bulk_create_annotation_maps_defect_to_opaque_platform_sample_id():
    with TestClient(app) as client:
        dataset_id = _create_sparse_sc_dataset(client, "SC Opaque Identity")
        platform_sample_id = "6594dbd1-46bd-4071-9968-61cd0240e1c0"
        _seed_sc_sparse_manifest(
            dataset_id,
            ["D001"],
            sample_ids_by_defect={"D001": platform_sample_id},
        )

        response = client.post(
            f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
            json={
                "annotations": [
                    {
                        "defect_id": "D001",
                        "label": "scratch",
                        "annotator": "user1",
                    }
                ]
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["created"] == 1
        annotations = client.get(
            f"/api/v1/datasets/{dataset_id}/samples/{platform_sample_id}/annotations"
        )
        assert annotations.status_code == 200, annotations.text
        assert [item["label"] for item in annotations.json()] == ["scratch"]


def test_bulk_create_annotation_zero_clears_existing_annotation():
    """SC code 0 is Unclassified and clears annotation instead of persisting label 0."""
    with TestClient(app) as client:
        dataset_id = _create_sparse_sc_dataset(client, "SC Bulk Sparse Clear")
        _seed_sc_sparse_manifest(dataset_id, ["D001"])

        create_resp = client.post(
            f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
            json={
                "annotations": [
                    {"defect_id": "D001", "label": "scratch", "annotator": "user1"},
                ],
            },
        )
        assert create_resp.status_code == 200, create_resp.text
        assert create_resp.json()["created"] == 1

        annotations_resp = client.get(
            f"/api/v1/datasets/{dataset_id}/samples/D001/annotations"
        )
        assert annotations_resp.status_code == 200, annotations_resp.text
        assert [ann["label"] for ann in annotations_resp.json()] == ["scratch"]

        clear_resp = client.post(
            f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
            json={
                "annotations": [
                    {"defect_id": "D001", "label": "0", "annotator": "user1"},
                ],
            },
        )
        assert clear_resp.status_code == 200, clear_resp.text
        assert clear_resp.json()["created"] == 0

        cleared_resp = client.get(
            f"/api/v1/datasets/{dataset_id}/samples/D001/annotations"
        )
        assert cleared_resp.status_code == 200, cleared_resp.text
        assert cleared_resp.json() == []


def test_bulk_create_annotations_empty_list():
    """Empty annotations list — should return created=0 without error."""
    with TestClient(app) as client:
        dataset_id = _create_sparse_sc_dataset(client, "SC Bulk Sparse Empty")
        _seed_sc_sparse_manifest(dataset_id, ["D001"])

        resp = client.post(
            f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
            json={"annotations": []},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["created"] == 0


def test_bulk_create_annotations_partial_unknown_defect_ids():
    """Unknown defect_id silently skipped; known defect_ids still annotated."""
    with TestClient(app) as client:
        dataset_id = _create_sparse_sc_dataset(client, "SC Bulk Sparse Partial")
        _seed_sc_sparse_manifest(dataset_id, ["D001", "D002"])

        resp = client.post(
            f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
            json={
                "annotations": [
                    {"defect_id": "D001", "label": "scratch", "annotator": "user1"},
                    {"defect_id": "NONEXISTENT", "label": "dust", "annotator": "user2"},
                    {"defect_id": "D002", "label": "clean", "annotator": "user3"},
                ],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["created"] == 2


def test_bulk_create_annotations_nonexistent_dataset_404():
    """Invalid dataset_id — should return 404."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/datasets/nonexistent-id/annotations/bulk-sc",
            json={
                "annotations": [
                    {"defect_id": "D001", "label": "scratch", "annotator": "user1"},
                ],
            },
        )
        assert resp.status_code == 404


# ── Sparse annotation mapping unit tests ─────────────────────────────


def test_map_defect_ids_via_sample_index():
    """Sparse defect identity resolves to independent platform sample IDs."""
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.sc.sc_dataset_agg import ScDatasetAgg
    from app.shared.api.schemas import DatasetStorageMode

    storage = MagicMock(
        dataset_id="ds-sparse-1",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
    )
    storage.map_upstream_item_ids_to_sample_ids = AsyncMock(
        return_value={"D001": "sample-uuid-1", "D002": "sample-uuid-2"}
    )
    db_lookup = MagicMock()
    db_lookup.map_defect_ids_to_sample_ids = AsyncMock()
    import asyncio as _asyncio

    result = _asyncio.run(
        ScDatasetAgg(storage, db_lookup).map_defect_ids_to_sample_ids(
            {"D001", "D002", "NONEXISTENT"}
        )
    )

    assert result == {"D001": "sample-uuid-1", "D002": "sample-uuid-2"}
    storage.map_upstream_item_ids_to_sample_ids.assert_awaited_once_with(
        {"D001", "D002", "NONEXISTENT"}
    )
    db_lookup.map_defect_ids_to_sample_ids.assert_not_awaited()


def test_map_defect_ids_via_db_lookup():
    """DB-full identity resolution is one explicit adapter query."""
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.sc.sc_dataset_agg import ScDatasetAgg
    from app.shared.api.schemas import DatasetStorageMode

    storage = MagicMock(
        dataset_id="ds-db-1",
        storage_mode=DatasetStorageMode.DB_FULL,
    )
    storage.map_upstream_item_ids_to_sample_ids = AsyncMock()
    db_lookup = MagicMock()
    db_lookup.map_defect_ids_to_sample_ids = AsyncMock(
        return_value={"D001": "sample-1"}
    )
    import asyncio as _asyncio

    result = _asyncio.run(
        ScDatasetAgg(storage, db_lookup).map_defect_ids_to_sample_ids({"D001"})
    )

    assert result == {"D001": "sample-1"}
    db_lookup.map_defect_ids_to_sample_ids.assert_awaited_once_with(
        "ds-db-1", {"D001"}
    )
    storage.map_upstream_item_ids_to_sample_ids.assert_not_awaited()
