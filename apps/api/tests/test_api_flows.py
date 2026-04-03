from fastapi.testclient import TestClient

from app.main import app


def test_dataset_and_job_flow() -> None:
    with TestClient(app) as c:
        ds = c.post("/api/v1/datasets", json={"name": "d1", "task_spec": {"task_type": "classification", "label_space": ["a", "b"]}})
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        preset = c.post(
            "/api/v1/training-presets",
            json={
                "name": "p1",
                "model_spec": {"framework": "pytorch", "base_model": "resnet18"},
                "omegaconf_yaml": "trainer:\n  max_epochs: 3",
                "dataloader_ref": "custom.loader:build",
            },
        )
        assert preset.status_code == 200
        preset_id = preset.json()["id"]

        job = c.post("/api/v1/training-jobs", json={"dataset_id": dataset_id, "preset_id": preset_id, "created_by": "u1"})
        assert job.status_code == 200
        job_id = job.json()["id"]

        r = c.get(f"/api/v1/training-jobs/{job_id}")
        assert r.status_code == 200


def test_get_dataset_detail() -> None:
    with TestClient(app) as c:
        created = c.post(
            "/api/v1/datasets",
            json={"name": "detail-ds", "task_spec": {"task_type": "classification", "label_space": ["x", "y"]}},
        )
        assert created.status_code == 200
        dataset_id = created.json()["id"]

        r = c.get(f"/api/v1/datasets/{dataset_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == dataset_id
        assert body["name"] == "detail-ds"
        assert body["task_spec"]["label_space"] == ["x", "y"]


def test_get_dataset_detail_not_found() -> None:
    with TestClient(app) as c:
        r = c.get("/api/v1/datasets/nonexistent-id-12345")
        assert r.status_code == 404
        assert r.json()["detail"] == "Dataset not found"


def test_get_preset_detail() -> None:
    with TestClient(app) as c:
        created = c.post(
            "/api/v1/training-presets",
            json={
                "name": "detail-preset",
                "model_spec": {"framework": "pytorch", "base_model": "resnet50"},
                "omegaconf_yaml": "trainer:\n  max_epochs: 5",
                "dataloader_ref": "custom.loader:build",
            },
        )
        assert created.status_code == 200
        preset_id = created.json()["id"]

        r = c.get(f"/api/v1/training-presets/{preset_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == preset_id
        assert body["name"] == "detail-preset"
        assert body["model_spec"]["base_model"] == "resnet50"


def test_get_preset_detail_not_found() -> None:
    with TestClient(app) as c:
        r = c.get("/api/v1/training-presets/nonexistent-id-12345")
        assert r.status_code == 404
        assert r.json()["detail"] == "Preset not found"


def test_samples_pagination() -> None:
    with TestClient(app) as c:
        # Create a dataset
        ds = c.post(
            "/api/v1/datasets",
            json={"name": "paginate-ds", "task_spec": {"task_type": "classification", "label_space": ["a", "b"]}},
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        # Create 3 samples
        for i in range(3):
            r = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={"image_uris": [f"s3://bucket/img{i}.jpg"]})
            assert r.status_code == 200

        # limit=2, offset=0 → 2 items, total=3
        r = c.get(f"/api/v1/datasets/{dataset_id}/samples?offset=0&limit=2")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2

        # offset=2, limit=50 → 1 item, total=3
        r = c.get(f"/api/v1/datasets/{dataset_id}/samples?offset=2&limit=50")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 1

        # default params → all 3 items, total=3
        r = c.get(f"/api/v1/datasets/{dataset_id}/samples")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3


def test_events_history_pagination() -> None:
    with TestClient(app) as c:
        # Set up dataset + preset + job
        ds = c.post(
            "/api/v1/datasets",
            json={"name": "event-ds", "task_spec": {"task_type": "classification", "label_space": ["a", "b"]}},
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        preset = c.post(
            "/api/v1/training-presets",
            json={
                "name": "event-preset",
                "model_spec": {"framework": "pytorch", "base_model": "resnet18"},
                "omegaconf_yaml": "trainer:\n  max_epochs: 1",
                "dataloader_ref": "custom.loader:build",
            },
        )
        assert preset.status_code == 200
        preset_id = preset.json()["id"]

        job = c.post(
            "/api/v1/training-jobs",
            json={"dataset_id": dataset_id, "preset_id": preset_id, "created_by": "tester"},
        )
        assert job.status_code == 200
        job_id = job.json()["id"]

        # History endpoint returns paginated response (may have events from orchestrator startup)
        r = c.get(f"/api/v1/training-jobs/{job_id}/events/history")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["total"] == len(body["items"])  # default limit=50 fetches all for a new job

        # Query with explicit offset/limit
        r = c.get(f"/api/v1/training-jobs/{job_id}/events/history?offset=0&limit=2")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert len(body["items"]) <= 2

        # 404 for unknown job
        r = c.get("/api/v1/training-jobs/nonexistent-job-xyz/events/history")
        assert r.status_code == 404


def test_auth_me() -> None:
    with TestClient(app) as c:
        r = c.get("/api/v1/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "dummy"
        assert body["name"] == "Local User"
        assert body["email"] == "user@local.dev"
        assert body["roles"] == ["admin"]


def test_auth_callback() -> None:
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/callback")
        assert r.status_code == 200
        body = r.json()
        assert body["token"] == "dummy-token"
        user = body["user"]
        assert user["id"] == "dummy"
        assert user["name"] == "Local User"
        assert user["email"] == "user@local.dev"
        assert user["roles"] == ["admin"]
