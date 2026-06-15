"""Integration tests for SC annotation bulk endpoint."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import DEFAULT_ORG_ID
from platform_runtime.sparse import DatasetManifest, SampleLocator

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


def _seed_sc_sparse_manifest(dataset_id: str, defect_ids: list[str]) -> None:
    """Write a DatasetManifest with sample_index into the app artifact storage.

    The manifest is placed at the canonical key so that
    ``DatasetPayloadStore.get_manifest()`` inside ``ScDatasetStore``
    finds it during bulk annotation mapping.
    """
    payload_store = app.state.app_context.datasets.dataset_payload_store

    sample_index: dict[str, SampleLocator] = {}
    for i, did in enumerate(defect_ids):
        sample_index[did] = SampleLocator(
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
    """Sparse dataset: map_defect_ids_to_sample_ids uses manifest sample_index."""
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.sc.adapter import ScDatasetReader, ScDatasetStore
    from app.shared.api.schemas import DatasetStorageMode
    from platform_runtime.sparse import DatasetManifest, DatasetPayloadStore, SampleLocator

    manifest = DatasetManifest(
        dataset_id="ds-sparse-1",
        storage_mode="file_shard_sparse",
        shard_count=1,
        total_rows=100,
        sample_index={
            "D001": SampleLocator(
                dataset_id="ds-sparse-1",
                shard_index=0,
                row_index=0,
                upstream_item_id="D001",
            ),
            "D002": SampleLocator(
                dataset_id="ds-sparse-1",
                shard_index=0,
                row_index=1,
                upstream_item_id="D002",
            ),
        },
    )

    mock_payload_store = MagicMock(spec=DatasetPayloadStore)
    mock_payload_store.get_manifest = AsyncMock(return_value=manifest)

    mock_reader = MagicMock(spec=ScDatasetReader)
    mock_reader.get_dataset = AsyncMock(return_value=MagicMock(
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
    ))

    store = ScDatasetStore(dataset_payload_store=mock_payload_store)
    import asyncio as _asyncio

    result = _asyncio.run(
        store.map_defect_ids_to_sample_ids(
            mock_reader,
            dataset_id="ds-sparse-1",
            defect_ids={"D001", "D002", "NONEXISTENT"},
            org_id="org-1",
        )
    )

    assert result == {"D001": "D001", "D002": "D002"}
    mock_payload_store.get_manifest.assert_called_once_with("ds-sparse-1", "org-1")
    mock_reader.list_samples.assert_not_called()


def test_map_defect_ids_via_sample_index_empty_manifest():
    """Empty sample_index — returns empty mapping without crashing."""
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.sc.adapter import ScDatasetStore
    from app.shared.api.schemas import DatasetStorageMode
    from platform_runtime.sparse import DatasetManifest, DatasetPayloadStore

    manifest = DatasetManifest(
        dataset_id="ds-sparse-2",
        storage_mode="file_shard_sparse",
        shard_count=1,
        total_rows=50,
        sample_index={},
    )

    mock_payload_store = MagicMock(spec=DatasetPayloadStore)
    mock_payload_store.get_manifest = AsyncMock(return_value=manifest)

    mock_reader = MagicMock()
    mock_reader.get_dataset = AsyncMock(return_value=MagicMock(
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
    ))

    store = ScDatasetStore(dataset_payload_store=mock_payload_store)
    import asyncio as _asyncio

    result = _asyncio.run(
        store.map_defect_ids_to_sample_ids(
            mock_reader,
            dataset_id="ds-sparse-2",
            defect_ids={"D001"},
            org_id="org-1",
        )
    )

    assert result == {}


def test_map_defect_ids_via_sample_index_manifest_not_found():
    """Manifest not found — returns empty mapping, no crash."""
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.sc.adapter import ScDatasetStore
    from app.shared.api.schemas import DatasetStorageMode
    from platform_runtime.sparse import DatasetPayloadStore

    mock_payload_store = MagicMock(spec=DatasetPayloadStore)
    mock_payload_store.get_manifest = AsyncMock(side_effect=FileNotFoundError("no manifest"))

    mock_reader = MagicMock()
    mock_reader.get_dataset = AsyncMock(return_value=MagicMock(
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
    ))

    store = ScDatasetStore(dataset_payload_store=mock_payload_store)
    import asyncio as _asyncio

    result = _asyncio.run(
        store.map_defect_ids_to_sample_ids(
            mock_reader,
            dataset_id="ds-sparse-3",
            defect_ids={"D001"},
            org_id="org-1",
        )
    )

    assert result == {}


def test_map_defect_ids_unknown_defect_ids_empty():
    """Unknown defect_ids return empty mapping without crashing."""
    from unittest.mock import AsyncMock, MagicMock

    from app.modules.sc.adapter import ScDatasetStore
    from app.shared.api.schemas import DatasetStorageMode
    from platform_runtime.sparse import DatasetManifest, DatasetPayloadStore, SampleLocator

    manifest = DatasetManifest(
        dataset_id="ds-sparse-4",
        storage_mode="file_shard_sparse",
        shard_count=1,
        total_rows=10,
        sample_index={
            "D003": SampleLocator(
                dataset_id="ds-sparse-4",
                shard_index=0,
                row_index=2,
                upstream_item_id="D003",
            ),
        },
    )

    mock_payload_store = MagicMock(spec=DatasetPayloadStore)
    mock_payload_store.get_manifest = AsyncMock(return_value=manifest)

    mock_reader = MagicMock()
    mock_reader.get_dataset = AsyncMock(return_value=MagicMock(
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
    ))

    store = ScDatasetStore(dataset_payload_store=mock_payload_store)
    import asyncio as _asyncio

    result = _asyncio.run(
        store.map_defect_ids_to_sample_ids(
            mock_reader,
            dataset_id="ds-sparse-4",
            defect_ids={"UNKNOWN_DEFECT"},
            org_id="org-1",
        )
    )

    assert result == {}
