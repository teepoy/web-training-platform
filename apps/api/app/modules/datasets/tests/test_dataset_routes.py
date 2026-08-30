"""Route-level tests for dataset endpoints.

Covers:
- PATCH /datasets/{id}/public
- POST  /datasets/{id}/annotations/bulk
- GET   /datasets/{id}/similarity/{sample_id}
- POST  /datasets/{id}/samples/import — label_space invariance
"""
from __future__ import annotations

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.modules.datasets.app.services.sample_similarity import SampleSimilarityService
from tests.conftest import DEFAULT_ORG_ID
from app.modules.storage.domain.sparse import DatasetManifest, SampleLocator

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


def _create_dataset(c: TestClient) -> str:
    resp = c.post("/api/v1/datasets", json={
        "name": "ds-route-test",
        "dataset_type": "image_classification",
        "task_spec": _TASK_SPEC,
    })
    assert resp.status_code == 200
    return resp.json()["id"]


def _create_sample(c: TestClient, dataset_id: str) -> str:
    resp = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={
        "image_uris": [],
        "metadata": {},
    })
    assert resp.status_code == 200
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Public visibility is disabled
# ---------------------------------------------------------------------------

def test_set_dataset_public_disabled() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        resp = c.patch(f"/api/v1/datasets/{dataset_id}/public", json={"is_public": True})
        assert resp.status_code == 410
        assert resp.json()["detail"] == "Make Public is disabled"


def test_set_dataset_public_disabled_for_missing_dataset() -> None:
    with TestClient(app) as c:
        resp = c.patch("/api/v1/datasets/nonexistent/public", json={"is_public": True})
        assert resp.status_code == 410
        assert resp.json()["detail"] == "Make Public is disabled"


def _seed_sparse_manifest(dataset_id: str, sample_ids: list[str]) -> None:
    """Seed a minimal sparse DatasetManifest so samples have identities."""
    payload_store = app.state.app_context.storage.dataset_payload_store

    sample_index: dict[str, SampleLocator] = {}
    for i, sid in enumerate(sample_ids):
        sample_index[sid] = SampleLocator(
            dataset_id=dataset_id,
            shard_index=0,
            row_index=i,
            upstream_item_id=sid,
        )

    manifest = DatasetManifest(
        dataset_id=dataset_id,
        storage_mode="file_shard_sparse",
        shard_count=1,
        total_rows=len(sample_ids),
        sample_index=sample_index,
    )

    asyncio.run(payload_store.put_manifest(manifest, org_id=DEFAULT_ORG_ID))


# ---------------------------------------------------------------------------
# Bulk annotations
# ---------------------------------------------------------------------------

def test_bulk_create_annotations() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        s1 = _create_sample(c, dataset_id)
        s2 = _create_sample(c, dataset_id)

        resp = c.post(f"/api/v1/datasets/{dataset_id}/annotations/bulk", json={
            "annotations": [
                {"sample_id": s1, "label": "cat"},
                {"sample_id": s2, "label": "dog"},
            ],
        })
        assert resp.status_code == 200
        assert resp.json()["created"] == 2


def test_bulk_create_annotations_dataset_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/datasets/nonexistent/annotations/bulk", json={
            "annotations": [{"sample_id": "x", "label": "cat"}],
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Similarity search
# ---------------------------------------------------------------------------

def test_similarity_search() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        sample_id = _create_sample(c, dataset_id)

        mock_result = {"neighbors": [], "sample_id": sample_id}
        with patch.object(
            SampleSimilarityService, "similarity_search",
            new_callable=AsyncMock, return_value=mock_result,
        ):
            resp = c.get(f"/api/v1/datasets/{dataset_id}/similarity/{sample_id}")
        assert resp.status_code == 200
        assert resp.json()["sample_id"] == sample_id


def test_similarity_search_dataset_not_found() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/datasets/nonexistent/similarity/some-sample")
        assert resp.status_code == 404


def test_similarity_search_sample_not_found() -> None:
    with TestClient(app) as c:
        dataset_id = _create_dataset(c)
        resp = c.get(f"/api/v1/datasets/{dataset_id}/similarity/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Samples import — configured label_space invariance
#
# Pre-fix regression test: importing a sample whose label is outside the
# Observed sample labels must not mutate the configured task_spec.label_space.
# ---------------------------------------------------------------------------


def _apply_test_overrides() -> None:
    """Install auth + LS mocks directly on app.dependency_overrides.

    This test file lives under app/modules/datasets/tests/ so the autouse
    fixtures from tests/conftest.py are NOT discovered here.  We set up the
    same mocks explicitly.
    """
    from app.modules.auth.port.http.deps import get_current_user, get_current_org
    from app.modules.datasets.port.http.deps import (
        get_label_studio_client as datasets_get_ls_client,
    )
    from app.modules.agent.port.http.deps import (
        get_label_studio_client as agent_get_ls_client,
    )
    from app.shared.api.schemas import User, Organization

    _mock_user = User(
        id="00000000-0000-0000-0000-000000000002",
        email="test@test.com",
        name="Test User",
        is_superadmin=True,
        is_active=True,
        created_at=datetime.datetime(2024, 1, 1),
    )
    _mock_org = Organization(
        id="00000000-0000-0000-0000-000000000001",
        name="Default",
        slug="default",
        created_at=datetime.datetime(2024, 1, 1),
    )

    _mock_ls = MagicMock()
    _mock_ls.create_project = AsyncMock(return_value={"id": 1, "title": "mock-project"})
    _mock_ls.update_project = AsyncMock(return_value={"id": 1, "title": "mock-project"})
    _mock_ls.delete_project = AsyncMock(return_value=None)
    _mock_ls.create_task = AsyncMock(return_value={"id": 1})
    _mock_ls.import_tasks = AsyncMock(
        side_effect=lambda project_id, tasks, return_task_ids=True: {
            "task_ids": list(range(1, len(tasks) + 1)),
            "task_count": len(tasks),
        }
    )
    _mock_ls.create_annotation = AsyncMock(return_value={"id": 0, "task": 0, "result": []})
    _mock_ls.list_tasks = AsyncMock(return_value=([], 0))
    _mock_ls.list_annotations = AsyncMock(return_value=[])
    _mock_ls.export_project = AsyncMock(return_value=[])

    app.dependency_overrides[get_current_user] = lambda: _mock_user
    app.dependency_overrides[get_current_org] = lambda: _mock_org
    app.dependency_overrides[datasets_get_ls_client] = lambda: _mock_ls
    app.dependency_overrides[agent_get_ls_client] = lambda: _mock_ls


def _cleanup_test_overrides() -> None:
    """Remove auth + LS dependency overrides installed by _apply_test_overrides()."""
    from app.modules.auth.port.http.deps import get_current_user, get_current_org
    from app.modules.datasets.port.http.deps import (
        get_label_studio_client as datasets_get_ls_client,
    )
    from app.modules.agent.port.http.deps import (
        get_label_studio_client as agent_get_ls_client,
    )

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_org, None)
    app.dependency_overrides.pop(datasets_get_ls_client, None)
    app.dependency_overrides.pop(agent_get_ls_client, None)


def test_import_samples_does_not_mutate_configured_label_space() -> None:
    """Importing observed labels preserves the configured taxonomy."""
    try:
        _apply_test_overrides()
        with TestClient(app) as c:
            # Create dataset with label_space ["cat", "dog"]
            dataset_id = _create_dataset(c)

            # Import a sample with label="bird" — outside current label_space
            import_resp = c.post(
                f"/api/v1/datasets/{dataset_id}/samples/import",
                json={
                    "items": [
                        {
                            "image_uris": ["memory://samples/bird.jpg"],
                            "metadata": {"index": 1},
                            "label": "bird",
                        },
                    ],
                },
            )
            assert import_resp.status_code == 200
            assert import_resp.json()["imported"] == 1

            # Fetch dataset and inspect label_space
            get_resp = c.get(f"/api/v1/datasets/{dataset_id}")
            assert get_resp.status_code == 200
            body = get_resp.json()

            task_spec = body["task_spec"]
            label_space = task_spec["label_space"]

            assert label_space == ["cat", "dog"]
    finally:
        # Clean up dependency_overrides so _assert_clean_overrides passes
        from app.modules.auth.port.http.deps import get_current_user, get_current_org
        from app.modules.datasets.port.http.deps import (
            get_label_studio_client as datasets_get_ls_client,
        )
        from app.modules.agent.port.http.deps import (
            get_label_studio_client as agent_get_ls_client,
        )

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_org, None)
        app.dependency_overrides.pop(datasets_get_ls_client, None)
        app.dependency_overrides.pop(agent_get_ls_client, None)


# ---------------------------------------------------------------------------
# Bulk annotation — configured label_space invariance (db_full)
# ---------------------------------------------------------------------------


def test_bulk_annotations_do_not_mutate_configured_label_space() -> None:
    _apply_test_overrides()
    try:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c)

            # Create 200 samples
            sample_ids = [_create_sample(c, dataset_id) for _ in range(200)]

            # Annotate first 100 with "bird"
            resp = c.post(
                f"/api/v1/datasets/{dataset_id}/annotations/bulk",
                json={
                    "annotations": [
                        {"sample_id": sid, "label": "bird"}
                        for sid in sample_ids[:100]
                    ],
                },
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["created"] == 100

            # Annotate remaining 100 with "fish"
            resp = c.post(
                f"/api/v1/datasets/{dataset_id}/annotations/bulk",
                json={
                    "annotations": [
                        {"sample_id": sid, "label": "fish"}
                        for sid in sample_ids[100:]
                    ],
                },
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["created"] == 100

            stats = c.get(f"/api/v1/datasets/{dataset_id}/annotation-stats")
            assert stats.status_code == 200, stats.text
            assert stats.json()["label_counts"] == {"bird": 100, "fish": 100}

            resp = c.get(f"/api/v1/datasets/{dataset_id}")
            assert resp.status_code == 200
            label_space = resp.json()["task_spec"]["label_space"]
            assert label_space == ["cat", "dog"]
    finally:
        _cleanup_test_overrides()


# ---------------------------------------------------------------------------
# Bulk annotation — configured label_space invariance (file_shard_sparse)
# ---------------------------------------------------------------------------


def test_sparse_bulk_annotations_do_not_mutate_configured_label_space() -> None:
    _apply_test_overrides()
    try:
        with TestClient(app) as c:
            # Create sparse SC dataset with label_space ["cat", "dog"]
            resp = c.post(
                "/api/v1/datasets",
                json={
                    "name": "sparse-bulk-test",
                    "dataset_type": "image_sc",
                    "task_spec": {"task_type": "sc", "label_space": ["cat", "dog"]},
                    "storage_mode": "file_shard_sparse",
                },
            )
            assert resp.status_code == 200, resp.text
            dataset_id = resp.json()["id"]

            # Seed a minimal sparse manifest with 200 sample IDs
            _seed_sparse_manifest(dataset_id, [f"S{i:04d}" for i in range(200)])

            # Annotate first 100 with "bird"
            resp = c.post(
                f"/api/v1/datasets/{dataset_id}/annotations/bulk",
                json={
                    "annotations": [
                        {"sample_id": f"S{i:04d}", "label": "bird"}
                        for i in range(100)
                    ],
                },
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["created"] == 100

            # Annotate remaining 100 with "fish"
            resp = c.post(
                f"/api/v1/datasets/{dataset_id}/annotations/bulk",
                json={
                    "annotations": [
                        {"sample_id": f"S{i:04d}", "label": "fish"}
                        for i in range(100, 200)
                    ],
                },
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["created"] == 100

            stats = c.get(f"/api/v1/datasets/{dataset_id}/annotation-stats")
            assert stats.status_code == 200, stats.text
            assert stats.json()["label_counts"] == {"bird": 100, "fish": 100}

            resp = c.get(f"/api/v1/datasets/{dataset_id}")
            assert resp.status_code == 200
            label_space = resp.json()["task_spec"]["label_space"]
            assert label_space == ["cat", "dog"]
    finally:
        _cleanup_test_overrides()
