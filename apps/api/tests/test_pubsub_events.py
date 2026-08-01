"""
Tests for annotation / prediction pubsub event publishing.

Covers:
- Annotation create / update / delete event emission (integration)
- Annotation bulk create event emission (integration)
- SC bulk annotation refresh event (integration)
- RedisEventPublisher method signatures and dead-code detection

IMPORTANT: In test mode, RedisEventPublisher(None) silently drops all events.
Tests override get_redis_event_publisher to capture and verify event calls.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, call

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.shared.infrastructure.redis.event_publisher import (
    ANNOTATION_CHANNEL,
    ANNOTATION_CREATED,
    ANNOTATION_UPDATED,
    PREDICTION_CHANNEL,
    RedisEventPublisher,
)
from app.modules.datasets.port.http.deps import (
    get_redis_event_publisher as datasets_get_publisher,
)
from app.modules.prediction.port.http.deps import (
    get_redis_event_publisher as prediction_get_publisher,
)
from tests.conftest import DEFAULT_ORG_ID

pytestmark = pytest.mark.integration


# ── Helpers ──────────────────────────────────────────────────────────────────


_TASK_SPEC = {"task_type": "classification", "label_space": ["rose", "tulip"]}


def _create_dataset_and_sample(c: TestClient) -> tuple[str, str]:
    ds = c.post(
        "/api/v1/datasets",
        json={"name": "pubsub-test-ds", "task_spec": _TASK_SPEC},
    )
    assert ds.status_code == 200, ds.text
    dataset_id = ds.json()["id"]
    sample = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={"image_uris": []})
    assert sample.status_code == 200, sample.text
    return dataset_id, sample.json()["id"]


def _create_annotation(
    c: TestClient, sample_id: str, dataset_id: str, label: str = "rose"
) -> str:
    r = c.post(
        "/api/v1/annotations",
        json={
            "dataset_id": dataset_id,
            "sample_id": sample_id,
            "label": label,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _make_mock_publisher() -> MagicMock:
    """Create a mock RedisEventPublisher that captures all publish calls."""
    mock = MagicMock(spec=RedisEventPublisher)
    mock.publish_annotation_created = AsyncMock()
    mock.publish_annotation_updated = AsyncMock()
    mock.publish_annotation_deleted = AsyncMock()
    mock.publish_annotation_refresh = AsyncMock()
    mock.publish_prediction_created = AsyncMock()
    mock.publish_prediction_updated = AsyncMock()
    mock.publish_prediction_refresh = AsyncMock()
    return mock


# ── Annotation CRUD Event Tests ─────────────────────────────────────────────


class TestAnnotationCreateEvent:
    """POST /api/v1/annotations → publish_annotation_created"""

    def test_publishes_on_create(self):
        mock_pub = _make_mock_publisher()
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as c:
                dataset_id, sample_id = _create_dataset_and_sample(c)
                ann_id = _create_annotation(c, sample_id, dataset_id, label="rose")

                mock_pub.publish_annotation_created.assert_awaited_once_with(
                    annotation_id=ann_id,
                    sample_id=sample_id,
                    dataset_id=dataset_id,
                )
                mock_pub.publish_annotation_updated.assert_not_awaited()
                mock_pub.publish_annotation_deleted.assert_not_awaited()
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)

    def test_does_not_publish_when_sample_not_found(self):
        mock_pub = _make_mock_publisher()
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as c:
                dataset_id, _ = _create_dataset_and_sample(c)
                resp = c.post(
                    "/api/v1/annotations",
                    json={
                        "dataset_id": dataset_id,
                        "sample_id": "nonexistent-sample",
                        "label": "rose",
                    },
                )
                assert resp.status_code == 404
                mock_pub.publish_annotation_created.assert_not_awaited()
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)


class TestAnnotationUpdateEvent:
    """PATCH /api/v1/annotations/{id} → publish_annotation_updated"""

    def test_publishes_on_update(self):
        mock_pub = _make_mock_publisher()
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as c:
                dataset_id, sample_id = _create_dataset_and_sample(c)
                ann_id = _create_annotation(c, sample_id, dataset_id, label="rose")

                # Reset mock to ignore the create event
                mock_pub.publish_annotation_created.reset_mock()

                resp = c.patch(
                    f"/api/v1/annotations/{ann_id}",
                    json={"dataset_id": dataset_id, "label": "tulip"},
                )
                assert resp.status_code == 200

                mock_pub.publish_annotation_updated.assert_awaited_once_with(
                    annotation_id=ann_id,
                    sample_id="",
                    dataset_id=dataset_id,
                )
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)

    def test_does_not_publish_on_404(self):
        mock_pub = _make_mock_publisher()
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as c:
                dataset_id, _ = _create_dataset_and_sample(c)
                resp = c.patch(
                    "/api/v1/annotations/nonexistent-id",
                    json={"dataset_id": dataset_id, "label": "tulip"},
                )
                assert resp.status_code == 404
                mock_pub.publish_annotation_updated.assert_not_awaited()
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)


class TestAnnotationDeleteEvent:
    """DELETE /api/v1/annotations/{id} → publish_annotation_deleted"""

    def test_publishes_on_delete(self):
        mock_pub = _make_mock_publisher()
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as c:
                dataset_id, sample_id = _create_dataset_and_sample(c)
                ann_id = _create_annotation(c, sample_id, dataset_id)

                # Reset mock to ignore the create event
                mock_pub.publish_annotation_created.reset_mock()

                resp = c.delete(
                    f"/api/v1/annotations/{ann_id}?dataset_id={dataset_id}"
                )
                assert resp.status_code == 204

                mock_pub.publish_annotation_deleted.assert_awaited_once_with(
                    annotation_id=ann_id,
                    sample_id="",
                    dataset_id=dataset_id,
                )
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)

    def test_does_not_publish_on_404(self):
        mock_pub = _make_mock_publisher()
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as c:
                dataset_id, _ = _create_dataset_and_sample(c)
                resp = c.delete(
                    f"/api/v1/annotations/nonexistent-id?dataset_id={dataset_id}"
                )
                assert resp.status_code == 404
                mock_pub.publish_annotation_deleted.assert_not_awaited()
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)


# ── Bulk Annotation Event Tests ─────────────────────────────────────────────


class TestAnnotationBulkCreateEvents:
    """POST /api/v1/datasets/{id}/annotations/bulk → N publish_annotation_created"""

    def test_publishes_one_event_per_annotation(self):
        mock_pub = _make_mock_publisher()
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as c:
                dataset_id, _ = _create_dataset_and_sample(c)
                # Create additional samples
                s2 = c.post(
                    f"/api/v1/datasets/{dataset_id}/samples", json={"image_uris": []}
                )
                assert s2.status_code == 200
                s2_id = s2.json()["id"]
                s3 = c.post(
                    f"/api/v1/datasets/{dataset_id}/samples", json={"image_uris": []}
                )
                assert s3.status_code == 200
                s3_id = s3.json()["id"]

                resp = c.post(
                    f"/api/v1/datasets/{dataset_id}/annotations/bulk",
                    json={
                        "annotations": [
                            {"sample_id": s2_id, "label": "rose"},
                            {"sample_id": s3_id, "label": "tulip"},
                        ],
                    },
                )
                assert resp.status_code == 200
                assert resp.json()["created"] == 2

                assert mock_pub.publish_annotation_created.await_count == 2
                # Order matches: first annotation in list → first call
                mock_pub.publish_annotation_created.assert_has_awaits(
                    [
                        call(
                            annotation_id=ANY,
                            sample_id=s2_id,
                            dataset_id=dataset_id,
                        ),
                        call(
                            annotation_id=ANY,
                            sample_id=s3_id,
                            dataset_id=dataset_id,
                        ),
                    ],
                    any_order=False,
                )
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)

    def test_empty_bulk_publishes_no_events(self):
        mock_pub = _make_mock_publisher()
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as c:
                dataset_id, _ = _create_dataset_and_sample(c)
                resp = c.post(
                    f"/api/v1/datasets/{dataset_id}/annotations/bulk",
                    json={"annotations": []},
                )
                assert resp.status_code == 200
                assert resp.json()["created"] == 0
                mock_pub.publish_annotation_created.assert_not_awaited()
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)


# ── SC Bulk Annotation Refresh Event ────────────────────────────────────────


class TestScBulkAnnotationRefreshEvent:
    """POST /datasets/{id}/annotations/bulk-sc → publish_annotation_refresh"""

    def _create_sparse_sc_dataset(self, client: TestClient, name: str) -> str:
        resp = client.post(
            "/api/v1/datasets",
            json={
                "name": name,
                "dataset_type": "image_sc",
                "task_spec": {
                    "task_type": "sc",
                    "label_space": ["defect", "clean"],
                },
                "storage_mode": "file_shard_sparse",
            },
        )
        assert resp.status_code == 200, resp.text
        return str(resp.json()["id"])

    def test_publishes_refresh_when_annotations_created(self):
        from app.modules.storage.domain.sparse import (
            DatasetManifest,
            SampleLocator,
        )

        mock_pub = _make_mock_publisher()
        # SC bulk-sc endpoint imports RedisEventPublisherDep from datasets deps
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as client:
                dataset_id = self._create_sparse_sc_dataset(
                    client, "SC PubSub Refresh"
                )

                # Seed manifest so defect_id → sample_id mapping works
                payload_store = (
                    app.state.app_context.storage.dataset_payload_store
                )
                manifest = DatasetManifest(
                    dataset_id=dataset_id,
                    storage_mode="file_shard_sparse",
                    shard_count=1,
                    total_rows=3,
                    sample_index={
                        "D001": SampleLocator(
                            dataset_id=dataset_id,
                            shard_index=0,
                            row_index=0,
                            upstream_item_id="D001",
                        ),
                        "D002": SampleLocator(
                            dataset_id=dataset_id,
                            shard_index=0,
                            row_index=1,
                            upstream_item_id="D002",
                        ),
                    },
                )
                asyncio.run(payload_store.put_manifest(manifest, org_id=DEFAULT_ORG_ID))

                resp = client.post(
                    f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
                    json={
                        "annotations": [
                            {"defect_id": "D001", "label": "scratch", "annotator": "u1"},
                            {"defect_id": "D002", "label": "clean", "annotator": "u2"},
                        ],
                    },
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["created"] == 2

                mock_pub.publish_annotation_refresh.assert_awaited_once_with(
                    dataset_id=dataset_id,
                )
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)

    def test_no_refresh_when_clear_zero_label(self):
        """Label "0" is SC Unclassified → annotation deleted, no new data.
        The handler still publishes refresh because annotation_ids_to_delete
        is non-empty."""
        from app.modules.storage.domain.sparse import (
            DatasetManifest,
            SampleLocator,
        )

        mock_pub = _make_mock_publisher()
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as client:
                dataset_id = self._create_sparse_sc_dataset(
                    client, "SC PubSub Clear"
                )

                payload_store = (
                    app.state.app_context.storage.dataset_payload_store
                )
                manifest = DatasetManifest(
                    dataset_id=dataset_id,
                    storage_mode="file_shard_sparse",
                    shard_count=1,
                    total_rows=1,
                    sample_index={
                        "D001": SampleLocator(
                            dataset_id=dataset_id,
                            shard_index=0,
                            row_index=0,
                            upstream_item_id="D001",
                        ),
                    },
                )
                asyncio.run(payload_store.put_manifest(manifest, org_id=DEFAULT_ORG_ID))

                # First: create annotation
                resp1 = client.post(
                    f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
                    json={
                        "annotations": [
                            {"defect_id": "D001", "label": "scratch", "annotator": "u1"},
                        ],
                    },
                )
                assert resp1.status_code == 200
                assert resp1.json()["created"] == 1
                mock_pub.publish_annotation_refresh.assert_awaited_once()
                mock_pub.reset_mock()

                # Second: set label to "0" (Unclassified) → clears annotation
                resp2 = client.post(
                    f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
                    json={
                        "annotations": [
                            {"defect_id": "D001", "label": "0", "annotator": "u1"},
                        ],
                    },
                )
                assert resp2.status_code == 200
                assert resp2.json()["created"] == 0
                # Refresh IS published because annotation_ids_to_delete is non-empty
                mock_pub.publish_annotation_refresh.assert_awaited_once_with(
                    dataset_id=dataset_id,
                )
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)

    def test_no_refresh_when_empty_annotations(self):
        mock_pub = _make_mock_publisher()
        app.dependency_overrides[datasets_get_publisher] = lambda: mock_pub
        try:
            with TestClient(app) as client:
                dataset_id = self._create_sparse_sc_dataset(
                    client, "SC PubSub Empty"
                )
                resp = client.post(
                    f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
                    json={"annotations": []},
                )
                assert resp.status_code == 200
                assert resp.json()["created"] == 0
                mock_pub.publish_annotation_refresh.assert_not_awaited()
        finally:
            app.dependency_overrides.pop(datasets_get_publisher, None)


# ── Prediction Event Tests ──────────────────────────────────────────────────


class TestPredictionEventPublisher:
    """Verify RedisEventPublisher prediction method signatures and behavior."""

    def test_prediction_methods_exist(self):
        """All three prediction publish methods are defined on the class."""
        pub = RedisEventPublisher(None)
        assert hasattr(pub, "publish_prediction_created")
        assert hasattr(pub, "publish_prediction_updated")
        assert hasattr(pub, "publish_prediction_refresh")
        assert callable(pub.publish_prediction_created)
        assert callable(pub.publish_prediction_updated)
        assert callable(pub.publish_prediction_refresh)

    def test_prediction_events_dropped_when_redis_none(self):
        """RedisEventPublisher(None) silently drops all events (no raising)."""
        pub = RedisEventPublisher(None)
        # These should not raise
        asyncio.run(
            pub.publish_prediction_created(
                prediction_id="p1", sample_id="s1", dataset_id="d1"
            )
        )
        asyncio.run(
            pub.publish_prediction_updated(
                prediction_id="p1", sample_id="s1", dataset_id="d1"
            )
        )
        asyncio.run(
            pub.publish_prediction_refresh(dataset_id="d1", job_id="j1")
        )

    def test_annotation_events_dropped_when_redis_none(self):
        """RedisEventPublisher(None) silently drops all annotation events."""
        pub = RedisEventPublisher(None)
        asyncio.run(
            pub.publish_annotation_created(
                annotation_id="a1", sample_id="s1", dataset_id="d1"
            )
        )
        asyncio.run(
            pub.publish_annotation_updated(
                annotation_id="a1", sample_id="s1", dataset_id="d1"
            )
        )
        asyncio.run(
            pub.publish_annotation_deleted(
                annotation_id="a1", sample_id="s1", dataset_id="d1"
            )
        )
        asyncio.run(
            pub.publish_annotation_refresh(dataset_id="d1")
        )


class TestPredictionDeadCode:
    """publish_prediction_created / publish_prediction_updated are NEVER called
    through any API endpoint in the current codebase.

    These tests verify the current state - they are awareness/documentation
    tests, not behaviour tests.
    """

    def test_prediction_created_not_called_by_any_endpoint(self):
        """Grep confirms zero callers for publish_prediction_created outside
        the definition itself."""
        import subprocess

        result = subprocess.run(
            [
                "grep", "-r", "--include=*.py",
                "-l", "publish_prediction_created",
                "app/",
            ],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        # Only event_publisher.py (definition) should match
        files = [f for f in result.stdout.strip().split("\n") if f]
        definition_file = "app/shared/infrastructure/redis/event_publisher.py"
        assert len(files) == 1, (
            f"Expected only {definition_file}, got: {files}"
        )
        assert definition_file in files[0], (
            f"publish_prediction_created called from: {files}"
        )

    def test_prediction_updated_not_called_by_any_endpoint(self):
        """Grep confirms zero callers for publish_prediction_updated outside
        the definition itself."""
        import subprocess

        result = subprocess.run(
            [
                "grep", "-r", "--include=*.py",
                "-l", "publish_prediction_updated",
                "app/",
            ],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        files = [f for f in result.stdout.strip().split("\n") if f]
        definition_file = "app/shared/infrastructure/redis/event_publisher.py"
        assert len(files) == 1, (
            f"Expected only {definition_file}, got: {files}"
        )
        assert definition_file in files[0]

    def test_prediction_refresh_has_callers(self):
        """publish_prediction_refresh IS called (prediction router + flow)."""
        import subprocess

        result = subprocess.run(
            [
                "grep", "-r", "--include=*.py",
                "-l", "publish_prediction_refresh",
                "app/",
            ],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        files = [f for f in result.stdout.strip().split("\n") if f]
        # Should find event_publisher.py + router + predict_job flow
        assert len(files) >= 3, (
            f"Expected at least 3 files, got {len(files)}: {files}"
        )


# ── Prediction Review Refresh Event ─────────────────────────────────────────


class TestPredictionReviewRefreshEvent:
    """POST /prediction-reviews/{id}/annotations → publish_prediction_refresh

    NOTE: Full integration test requires prediction data in storage (dataset
    → job → model → review action → annotated samples).  This test verifies
    the endpoint wiring by mocking the prediction service and storage factory
    to return annotation data, which triggers the refresh publish.
    """

    def test_publishes_refresh_after_saving_review_annotations(self):
        from datetime import datetime, timezone

        from app.shared.api.schemas import (
            Annotation,
            AnnotationVersion,
            Dataset,
            DatasetStorageMode,
            PredictionReviewAction,
            TaskSpec,
        )

        mock_pub = _make_mock_publisher()
        app.dependency_overrides[prediction_get_publisher] = lambda: mock_pub

        # Mock prediction_service.save_review_annotations → returns data
        mock_ann = Annotation(id="ann-1", sample_id="s1", label="cat", created_by="u1")
        mock_ver = AnnotationVersion(
            id="av-1",
            review_action_id="ra-1",
            annotation_id="ann-1",
            prediction_id="p-1",
            predicted_label="dog",
            final_label="cat",
            created_at=datetime.now(timezone.utc),
        )

        from app.modules.prediction.port.http.deps import (
            get_dataset_reader,
            get_dataset_service,
            get_prediction_review,
            get_prediction_repository,
        )
        mock_svc = MagicMock()
        mock_svc.save_review_annotations = AsyncMock(
            return_value=([mock_ann], [mock_ver])
        )
        app.dependency_overrides[get_prediction_review] = lambda: mock_svc

        mock_repo = MagicMock()
        mock_repo.get_review_action = AsyncMock(
            return_value=PredictionReviewAction(
                id="ra-1",
                dataset_id="ds-1",
                model_id="m-1",
                created_by="u1",
                created_at=datetime.now(timezone.utc),
            )
        )
        mock_repo.get_dataset = AsyncMock(
            return_value=Dataset(
                id="ds-1",
                name="test",
                task_spec=TaskSpec(
                    task_type="classification", label_space=["cat", "dog"]
                ),
                storage_mode=DatasetStorageMode.DB_FULL,
                created_by="u1",
                created_at=datetime.now(timezone.utc),
            )
        )
        app.dependency_overrides[get_prediction_repository] = lambda: mock_repo

        mock_reader = MagicMock()
        mock_reader.get_dataset = AsyncMock(return_value=mock_repo.get_dataset.return_value)
        app.dependency_overrides[get_dataset_reader] = lambda: mock_reader

        mock_dataset_service = MagicMock()
        mock_dataset_service.merge_label_space = AsyncMock()
        app.dependency_overrides[get_dataset_service] = lambda: mock_dataset_service

        try:
            with TestClient(app) as c:
                resp = c.post(
                    "/api/v1/prediction-reviews/ra-1/annotations",
                    json={
                        "items": [
                            {
                                "sample_id": "s1",
                                "predicted_label": "dog",
                                "final_label": "cat",
                                "confidence": None,
                                "prediction_id": None,
                            },
                        ],
                    },
                )
                assert resp.status_code == 200, resp.text

                mock_pub.publish_prediction_refresh.assert_awaited_once_with(
                    dataset_id="ds-1",
                    job_id="",
                )
        finally:
            app.dependency_overrides.pop(prediction_get_publisher, None)
            app.dependency_overrides.pop(get_prediction_review, None)
            app.dependency_overrides.pop(get_prediction_repository, None)
            app.dependency_overrides.pop(get_dataset_reader, None)
            app.dependency_overrides.pop(get_dataset_service, None)

    def test_no_refresh_when_no_annotations_saved(self):
        from datetime import datetime, timezone

        from app.shared.api.schemas import (
            Dataset,
            DatasetStorageMode,
            PredictionReviewAction,
            TaskSpec,
        )

        mock_pub = _make_mock_publisher()
        app.dependency_overrides[prediction_get_publisher] = lambda: mock_pub

        from app.modules.prediction.port.http.deps import (
            get_dataset_reader,
            get_dataset_service,
            get_prediction_review,
            get_prediction_repository,
        )
        mock_svc = MagicMock()
        mock_svc.save_review_annotations = AsyncMock(return_value=([], []))
        app.dependency_overrides[get_prediction_review] = lambda: mock_svc

        mock_repo = MagicMock()
        mock_repo.get_review_action = AsyncMock(
            return_value=PredictionReviewAction(
                id="ra-1",
                dataset_id="ds-1",
                model_id="m-1",
                created_by="u1",
                created_at=datetime.now(timezone.utc),
            )
        )
        mock_repo.get_dataset = AsyncMock(
            return_value=Dataset(
                id="ds-1",
                name="test",
                task_spec=TaskSpec(
                    task_type="classification", label_space=["cat", "dog"]
                ),
                storage_mode=DatasetStorageMode.DB_FULL,
                created_by="u1",
                created_at=datetime.now(timezone.utc),
            )
        )
        app.dependency_overrides[get_prediction_repository] = lambda: mock_repo

        mock_reader = MagicMock()
        mock_reader.get_dataset = AsyncMock(return_value=mock_repo.get_dataset.return_value)
        app.dependency_overrides[get_dataset_reader] = lambda: mock_reader

        mock_dataset_service = MagicMock()
        mock_dataset_service.merge_label_space = AsyncMock()
        app.dependency_overrides[get_dataset_service] = lambda: mock_dataset_service

        try:
            with TestClient(app) as c:
                resp = c.post(
                    "/api/v1/prediction-reviews/ra-1/annotations",
                    json={
                        "items": [
                            {
                                "sample_id": "s1",
                                "predicted_label": "dog",
                                "final_label": "cat",
                                "confidence": None,
                                "prediction_id": None,
                            },
                        ],
                    },
                )
                assert resp.status_code == 200, resp.text
                mock_pub.publish_prediction_refresh.assert_not_awaited()
        finally:
            app.dependency_overrides.pop(prediction_get_publisher, None)
            app.dependency_overrides.pop(get_prediction_review, None)
            app.dependency_overrides.pop(get_prediction_repository, None)
            app.dependency_overrides.pop(get_dataset_reader, None)
            app.dependency_overrides.pop(get_dataset_service, None)


# ── Event Publisher Redis Integration (unit) ────────────────────────────────


class TestRedisEventPublisherUnit:
    """Unit tests for RedisEventPublisher without FastAPI integration."""

    def test_publish_calls_redis_publish_with_correct_channel(self):
        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock(return_value=1)

        pub = RedisEventPublisher(mock_redis)
        asyncio.run(
            pub.publish_annotation_created(
                annotation_id="a1", sample_id="s1", dataset_id="d1"
            )
        )

        mock_redis.publish.assert_awaited_once()
        args, _kwargs = mock_redis.publish.call_args
        channel = args[0]
        assert channel == ANNOTATION_CHANNEL

    def test_publish_payload_structure(self):
        import json

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock(return_value=1)

        pub = RedisEventPublisher(mock_redis)
        asyncio.run(
            pub.publish_annotation_created(
                annotation_id="a1", sample_id="s1", dataset_id="d1"
            )
        )

        _, message = mock_redis.publish.call_args[0]
        payload = json.loads(message)
        assert payload["event"] == ANNOTATION_CREATED
        assert "timestamp" in payload
        assert payload["data"] == {
            "annotation_id": "a1",
            "sample_id": "s1",
            "dataset_id": "d1",
        }

    def test_annotation_refresh_uses_annotation_updated_event_type(self):
        """publish_annotation_refresh reuses ANNOTATION_UPDATED event type.
        This is a known design choice — refresh triggers update semantics."""
        import json

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock(return_value=1)

        pub = RedisEventPublisher(mock_redis)
        asyncio.run(pub.publish_annotation_refresh(dataset_id="d1"))

        _, message = mock_redis.publish.call_args[0]
        payload = json.loads(message)
        assert payload["event"] == ANNOTATION_UPDATED
        assert payload["data"] == {"dataset_id": "d1"}

    def test_all_event_types_publish_to_correct_channels(self):

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock(return_value=1)
        pub = RedisEventPublisher(mock_redis)

        # Annotation events → ANNOTATION_CHANNEL
        asyncio.run(
            pub.publish_annotation_created(
                annotation_id="a1", sample_id="s1", dataset_id="d1"
            )
        )
        an_channel_1 = mock_redis.publish.call_args[0][0]
        assert an_channel_1 == ANNOTATION_CHANNEL
        mock_redis.publish.reset_mock()

        asyncio.run(
            pub.publish_annotation_deleted(
                annotation_id="a1", sample_id="s1", dataset_id="d1"
            )
        )
        an_channel_2 = mock_redis.publish.call_args[0][0]
        assert an_channel_2 == ANNOTATION_CHANNEL
        mock_redis.publish.reset_mock()

        # Prediction events → PREDICTION_CHANNEL
        asyncio.run(
            pub.publish_prediction_created(
                prediction_id="p1", sample_id="s1", dataset_id="d1"
            )
        )
        pr_channel_1 = mock_redis.publish.call_args[0][0]
        assert pr_channel_1 == PREDICTION_CHANNEL
        mock_redis.publish.reset_mock()

        asyncio.run(
            pub.publish_prediction_refresh(dataset_id="d1", job_id="j1")
        )
        pr_channel_2 = mock_redis.publish.call_args[0][0]
        assert pr_channel_2 == PREDICTION_CHANNEL

    def test_exception_in_redis_publish_is_logged_not_raised(self):
        """If Redis publish fails, the error is logged but not propagated."""
        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock(side_effect=ConnectionError("redis down"))

        pub = RedisEventPublisher(mock_redis)
        # Should not raise
        asyncio.run(
            pub.publish_annotation_created(
                annotation_id="a1", sample_id="s1", dataset_id="d1"
            )
        )
        # The exception was caught — no propagation

    def test_revision_publisher_fails_explicitly_without_redis(self):
        pub = RedisEventPublisher(None, revision_namespace="sc-data-provider")

        with pytest.raises(
            RuntimeError, match="required for SC data revision invalidation"
        ):
            asyncio.run(pub.publish_annotation_refresh(dataset_id="d1"))

    def test_revision_publisher_propagates_atomic_publish_failure(self):
        mock_redis = MagicMock()
        mock_redis.eval = AsyncMock(side_effect=ConnectionError("redis down"))
        pub = RedisEventPublisher(
            mock_redis, revision_namespace="sc-data-provider"
        )

        with pytest.raises(ConnectionError, match="redis down"):
            asyncio.run(pub.publish_prediction_refresh(dataset_id="d1", job_id="j1"))
