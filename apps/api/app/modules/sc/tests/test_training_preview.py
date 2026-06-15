"""E2E test: SC (patch) dataset training and preview flow.

Covers:
- Create image_sc dataset with samples (dual-view: patch_image_v1 + review_image_v1)
- Generate labels via annotations
- Trigger training job with resnet50-sc-v1
- Verify training completes and checkpoint (model artifact) is generated
- Verify SC view endpoints work after training
"""

from __future__ import annotations

# pyright: reportPrivateImportUsage=false

import base64
import io
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

_SC_TASK_SPEC = {
    "task_type": "sc",
    "label_space": ["defect", "clean"],
}

_SC_TRAINER_ID = "resnet50-sc-v1"


def _make_data_uri() -> str:
    """Generate a tiny 1x1 gray PNG as a base64 data URI."""
    from PIL import Image

    img = Image.new("RGB", (1, 1), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


async def _verify_checkpoint(model_uri: str) -> None:
    """Load and validate a dual-ResNet-50 checkpoint saved by the SC trainer."""
    import io as _io

    import torch
    from torchvision import models

    from app.main import app

    storage = app.state.app_context.shared.artifact_storage
    raw = await storage.get_bytes(model_uri)
    checkpoint = torch.load(_io.BytesIO(raw), map_location="cpu", weights_only=False)

    assert "model_state_dict" in checkpoint, (
        f"Checkpoint missing model_state_dict, keys: {list(checkpoint.keys())}"
    )
    assert "labels" in checkpoint
    assert "num_classes" in checkpoint
    assert checkpoint["architecture"] == "dual-resnet50"
    assert checkpoint["framework"] == "pytorch"
    assert len(checkpoint["labels"]) >= 2

    num_classes = checkpoint["num_classes"]

    class DualResNetClassifier(torch.nn.Module):
        def __init__(self, num_classes: int) -> None:
            super().__init__()
            backbone = models.resnet50(weights=None)
            self.backbone = torch.nn.Sequential(*list(backbone.children())[:-1])
            self.classifier = torch.nn.Sequential(
                torch.nn.Linear(2048 * 3, 512),
                torch.nn.ReLU(),
                torch.nn.Dropout(0.3),
                torch.nn.Linear(512, num_classes),
            )

        def forward(
            self, defective: torch.Tensor, reference: torch.Tensor
        ) -> torch.Tensor:
            feat_d = self.backbone(defective).flatten(1)
            feat_r = self.backbone(reference).flatten(1)
            diff = torch.abs(feat_d - feat_r)
            combined = torch.cat([feat_d, feat_r, diff], dim=1)
            return self.classifier(combined)

    model = DualResNetClassifier(num_classes=int(num_classes))
    model.load_state_dict(checkpoint["model_state_dict"])

    assert model is not None


def _create_sc_dataset(client: TestClient, name: str = "SC E2E Test") -> str:
    """Create an image_sc dataset and return its ID."""
    resp = client.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "dataset_type": "image_sc",
            "task_spec": _SC_TASK_SPEC,
            "storage_mode": "file_shard_sparse",
        },
    )
    assert resp.status_code == 200, f"Create dataset failed: {resp.text}"
    return resp.json()["id"]


def _add_sc_sample(
    client: TestClient,
    dataset_id: str,
    defect_id: str = "D001",
    wafer_key: int = 1,
    has_review_images: bool = True,
) -> str:
    """Add a single SC sample with metadata and return its ID.

    Uses data: URIs so the ClassificationTrainer can decode them directly
    without needing artifact storage.
    """
    data_uri = _make_data_uri()

    metadata: dict = {
        "inspection_time": "2024-01-15T08:30:00",
        "wafer_key": wafer_key,
        "defect_id": defect_id,
        "lot_id": "LOT001",
        "wafer_x": 23,
        "wafer_y": 45,
        "rough_bin": 1,
        "class_number": 5,
    }
    if has_review_images:
        metadata["review_images"] = [
            {
                "image_url": "http://ex.com/review_1.png",
                "image_name": "review_1.png",
                "image_id": 1,
                "image_type": "review",
            }
        ]

    resp = client.post(
        f"/api/v1/datasets/{dataset_id}/samples",
        json={
            "image_uris": [data_uri],
            "metadata": metadata,
        },
    )
    assert resp.status_code == 200, f"Create sample failed: {resp.text}"
    return resp.json()["id"]


def _create_annotation(client: TestClient, sample_id: str, label: str) -> str:
    """Create an annotation for a sample and return annotation ID."""
    resp = client.post(
        "/api/v1/annotations",
        json={"sample_id": sample_id, "label": label},
    )
    assert resp.status_code == 200, f"Create annotation failed: {resp.text}"
    return resp.json()["id"]


def _wait_for_job(
    client: TestClient,
    job_id: str,
    timeout: int = 120,
    poll_interval: float = 1.0,
) -> dict:
    """Poll GET /api/v1/training-jobs/{job_id} until terminal state.

    Returns the final job response dict.
    """
    deadline = time.monotonic() + timeout
    last_status = ""
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/training-jobs/{job_id}")
        if resp.status_code == 404:
            raise RuntimeError(f"Job {job_id} not found (404)")
        assert resp.status_code == 200
        body = resp.json()
        status = body.get("status", "")
        last_status = status
        if status in ("completed", "failed"):
            return body
        time.sleep(poll_interval)
    raise RuntimeError(
        f"Job {job_id} timed out after {timeout}s (last status: {last_status})"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScTrainingE2E:
    """End-to-end SC training flow: dataset -> samples -> annotations -> train."""

    @pytest.mark.slow
    def test_sc_training_completes_with_checkpoint(self):
        """Full E2E: create SC dataset, annotate, train, verify checkpoint."""
        with TestClient(app) as client:
            # 1. Create SC dataset
            dataset_id = _create_sc_dataset(client, "SC Training E2E")

            # 2. Add samples with metadata (wafer coordinates, bin, review images)
            labels_cycle = ["defect", "clean"]
            sample_ids: list[str] = []
            for i in range(10):
                sample_id = _add_sc_sample(
                    client,
                    dataset_id,
                    defect_id=f"D{i + 1:03d}",
                    wafer_key=1,
                    has_review_images=(i % 2 == 0),  # half have review images
                )
                sample_ids.append(sample_id)

            # 3. Create annotations for each sample
            for i, sample_id in enumerate(sample_ids):
                label = labels_cycle[i % len(labels_cycle)]
                _create_annotation(client, sample_id, label)

            # 4. Trigger training job
            job_resp = client.post(
                "/api/v1/training-jobs",
                json={
                    "dataset_id": dataset_id,
                    "trainer_id": _SC_TRAINER_ID,
                },
            )
            assert job_resp.status_code == 200, (
                f"Create training job failed: {job_resp.text}"
            )
            job_id = job_resp.json()["id"]
            assert job_resp.json()["status"] in ("pending", "running")

            # 5. Wait for training to complete
            finished = _wait_for_job(client, job_id)
            assert finished["status"] == "completed", (
                f"Expected completed, got {finished['status']}: {finished}"
            )

            job_detail = client.get(f"/api/v1/training-jobs/{job_id}").json()
            artifact_refs = job_detail.get("artifact_refs", [])

            assert len(artifact_refs) >= 1, (
                f"Expected at least 1 artifact, got: {artifact_refs}"
            )

            model_artifact = next(
                (a for a in artifact_refs if a["kind"] == "model"), None
            )
            assert model_artifact is not None, (
                f"No model artifact found in: {artifact_refs}"
            )
            model_uri = model_artifact["uri"]

            import asyncio

            asyncio.run(_verify_checkpoint(model_uri))

    @pytest.mark.slow
    def test_sc_views_work_after_training(self):
        """SC view endpoints remain functional before and after training."""
        with TestClient(app) as client:
            dataset_id = _create_sc_dataset(client, "SC Views After Training")
            sample_1 = _add_sc_sample(client, dataset_id, defect_id="D001")
            sample_2 = _add_sc_sample(client, dataset_id, defect_id="D002")
            _create_annotation(client, sample_1, "defect")
            _create_annotation(client, sample_2, "clean")

            resp = client.get(
                f"/api/v1/datasets/{dataset_id}/views/patch_image_v1/samples"
            )
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) >= 1
            item = items[0]
            assert "sample_id" in item
            assert "defect_id" in item
            assert "inspection_time" in item

            job_resp = client.post(
                "/api/v1/training-jobs",
                json={
                    "dataset_id": dataset_id,
                    "trainer_id": _SC_TRAINER_ID,
                },
            )
            assert job_resp.status_code == 200
            job_id = job_resp.json()["id"]
            finished = _wait_for_job(client, job_id)
            assert finished["status"] == "completed"

            resp2 = client.get(
                f"/api/v1/datasets/{dataset_id}/views/patch_image_v1/samples"
            )
            assert resp2.status_code == 200
            assert len(resp2.json()["items"]) >= 1

            resp3 = client.get(
                f"/api/v1/datasets/{dataset_id}/views/review_image_v1/samples"
            )
            assert resp3.status_code == 200

            resp4 = client.get(
                f"/api/v1/datasets/{dataset_id}/views/patch_image_v1/samples"
            )
            assert resp4.status_code == 200

    @pytest.mark.slow
    def test_sc_trainer_registered_and_listable(self):
        """The SC trainer is discoverable via the trainers API."""
        with TestClient(app) as client:
            resp = client.get("/api/v1/trainers")
            assert resp.status_code == 200
            trainers = resp.json()
            trainer_ids = [t["id"] for t in trainers]
            assert _SC_TRAINER_ID in trainer_ids, (
                f"SC trainer {_SC_TRAINER_ID} not found in: {trainer_ids}"
            )

            # Verify the trainer detail
            resp2 = client.get(f"/api/v1/trainers/{_SC_TRAINER_ID}")
            assert resp2.status_code == 200
            detail = resp2.json()
            assert detail["id"] == _SC_TRAINER_ID
            assert detail["view_type"] == "patch_image_v1"
            assert detail["trainable"] is True
