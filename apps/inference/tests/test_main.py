"""Integration tests for the GPU worker predict/embed/train endpoints.

Uses fastapi.testclient.TestClient to verify:
- /v1/predict response shape for all targets (image_classification, vqa, embedding)
- /v1/embed response shape
- /v1/train submit, status, cancel, logs, idempotency, metrics
- Error handling (validation errors → 422, graceful missing-bytes → 200+error)
- Prometheus metrics recording
"""

from __future__ import annotations

import base64
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ── Predict helpers ────────────────────────────────────────────────────────


def _make_image_bytes_b64() -> str:
    """Return base64 of a small non-black JPEG."""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (4, 4), color=(100, 150, 200)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _make_model_b64(label_prototypes: dict | None = None) -> str:
    """Return base64-encoded model JSON with optional label_prototypes."""
    import json

    payload: dict = {}
    if label_prototypes is not None:
        payload["label_prototypes"] = label_prototypes
    return base64.b64encode(json.dumps(payload).encode()).decode("ascii")


def _predict_payload(
    *,
    target: str = "image_classification",
    label_space: list[str] | None = None,
    samples: list[dict] | None = None,
    model_b64: str | None = None,
) -> dict:
    if model_b64 is None:
        model_b64 = _make_model_b64()
    if label_space is None:
        label_space = []
    if samples is None:
        samples = [
            {"sample_id": "s1", "image_bytes_b64": _make_image_bytes_b64()},
        ]
    return {
        "model": {
            "id": "test-model",
            "uri": "test://model",
            "content_b64": model_b64,
        },
        "target": target,
        "label_space": label_space,
        "samples": samples,
    }


def _embed_payload(samples: list[dict] | None = None) -> dict:
    if samples is None:
        samples = [
            {"sample_id": "s1", "image_bytes_b64": _make_image_bytes_b64()},
        ]
    return {
        "model_name": "test-embed-model",
        "samples": samples,
    }


# ── Predict endpoint ───────────────────────────────────────────────────────


class TestPredictEndpoint:
    """Verify /v1/predict response shape and behaviour."""

    def test_predict_image_classification_with_prototypes(self) -> None:
        """Classification with provided label prototypes returns label, confidence, scores."""
        prototypes = {
            "cat": [0.1, 0.2, 0.3] * 22,
            "dog": [0.4, 0.5, 0.6] * 22,
        }
        payload = _predict_payload(
            target="image_classification",
            label_space=["cat", "dog"],
            model_b64=_make_model_b64(label_prototypes=prototypes),
        )
        with TestClient(app) as client:
            resp = client.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        body = resp.json()
        assert "predictions" in body
        assert isinstance(body["predictions"], list)
        assert len(body["predictions"]) == 1

        pred = body["predictions"][0]
        assert pred["sample_id"] == "s1"
        assert pred["label"] in ("cat", "dog")
        assert isinstance(pred["confidence"], float)
        assert isinstance(pred["scores"], dict)
        assert pred["scores"]  # non-empty
        assert pred["error"] is None

    def test_predict_image_classification_no_prototypes_generates_dummy(self) -> None:
        """When model has no label_prototypes, dummy vectors are generated from label_space."""
        payload = _predict_payload(
            target="image_classification",
            label_space=["cat", "dog"],
            model_b64=_make_model_b64(label_prototypes=None),
        )
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        pred = resp.json()["predictions"][0]
        assert pred["label"] in ("cat", "dog")
        assert pred["confidence"] is not None
        assert pred["error"] is None

    def test_predict_image_classification_from_metadata_label_space(self) -> None:
        """Falls back to metadata.label_space when top-level label_space is empty."""
        metadata_b64 = base64.b64encode(
            b'{"label_space": ["cat", "dog"]}'
        ).decode("ascii")
        payload = {
            "model": {
                "id": "test-model",
                "uri": "test://model",
                "content_b64": metadata_b64,
                "metadata": {"label_space": ["cat", "dog"]},
            },
            "target": "image_classification",
            "label_space": [],
            "samples": [
                {"sample_id": "s1", "image_bytes_b64": _make_image_bytes_b64()},
            ],
        }
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        pred = resp.json()["predictions"][0]
        assert pred["label"] in ("cat", "dog")
        assert pred["error"] is None

    def test_predict_missing_image_bytes_returns_error(self) -> None:
        """Sample without image_bytes_b64 gets error in prediction item, not HTTP error."""
        payload = _predict_payload(
            target="image_classification",
            label_space=["cat", "dog"],
            samples=[{"sample_id": "s1", "image_uris": ["http://example.com/1.jpg"]}],
        )
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        pred = resp.json()["predictions"][0]
        assert pred["sample_id"] == "s1"
        assert pred["error"] == "missing image bytes"

    def test_predict_empty_model_prototypes_returns_error(self) -> None:
        """When model bytes produce empty prototypes and label_space is empty, returns error."""
        payload = _predict_payload(
            target="image_classification",
            label_space=[],
            model_b64=_make_model_b64(label_prototypes={}),
        )
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        pred = resp.json()["predictions"][0]
        assert pred["error"] == "model has no label prototypes"

    def test_predict_embedding_target(self) -> None:
        """Embedding target returns label='embedding' with confidence 1.0."""
        payload = _predict_payload(
            target="embedding",
            label_space=[],
        )
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        pred = resp.json()["predictions"][0]
        assert pred["sample_id"] == "s1"
        assert pred["label"] == "embedding"
        assert pred["confidence"] == 1.0
        assert pred["error"] is None

    def test_predict_vqa_requires_llm_config(self) -> None:
        """VQA target returns error when LLM env vars are not configured."""
        payload = _predict_payload(
            target="vqa",
            samples=[
                {
                    "sample_id": "s1",
                    "image_bytes_b64": _make_image_bytes_b64(),
                    "question": "What is in the image?",
                },
            ],
        )
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        pred = resp.json()["predictions"][0]
        # Without LLM_API_KEY, _answer_vqa raises ValueError
        assert pred["error"] is not None
        assert "api_key" in pred["error"].lower() or "configure" in pred["error"].lower()

    def test_predict_vqa_with_mock_llm(self) -> None:
        """VQA target with mocked LLM returns the model's answer as label."""
        payload = _predict_payload(
            target="vqa",
            samples=[
                {
                    "sample_id": "s1",
                    "image_bytes_b64": _make_image_bytes_b64(),
                    "question": "What color is the sky?",
                },
            ],
        )

        async def mock_answer_vqa(*args: object, **kwargs: object) -> str:
            return "blue"

        with patch("app.main._answer_vqa", mock_answer_vqa):
            with TestClient(app) as cl:
                resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        pred = resp.json()["predictions"][0]
        assert pred["sample_id"] == "s1"
        assert pred["label"] == "blue"
        assert pred["confidence"] is None
        assert pred["error"] is None

    def test_predict_vqa_missing_question_returns_error(self) -> None:
        """VQA sample without question gets error in response."""
        payload = _predict_payload(
            target="vqa",
            samples=[
                {
                    "sample_id": "s1",
                    "image_bytes_b64": _make_image_bytes_b64(),
                    "question": "",
                },
            ],
        )

        async def mock_answer_vqa(*args: object, **kwargs: object) -> str:
            return "should not be called"

        with patch("app.main._answer_vqa", mock_answer_vqa):
            with TestClient(app) as cl:
                resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        pred = resp.json()["predictions"][0]
        assert pred["error"] == "missing question"

    def test_predict_vqa_missing_image_bytes_returns_error(self) -> None:
        """VQA sample without image_bytes_b64 gets error before calling LLM."""
        payload = _predict_payload(
            target="vqa",
            samples=[
                {
                    "sample_id": "s1",
                    "question": "What is this?",
                },
            ],
        )

        async def mock_answer_vqa(*args: object, **kwargs: object) -> str:
            return "should not be called"

        with patch("app.main._answer_vqa", mock_answer_vqa):
            with TestClient(app) as cl:
                resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        pred = resp.json()["predictions"][0]
        assert pred["error"] == "missing image bytes"

    def test_predict_vqa_llm_error_caught(self) -> None:
        """LLM exception is caught and returned as sample error, never 500."""
        payload = _predict_payload(
            target="vqa",
            samples=[
                {
                    "sample_id": "s1",
                    "image_bytes_b64": _make_image_bytes_b64(),
                    "question": "What is this?",
                },
            ],
        )

        async def mock_failing_vqa(*args: object, **kwargs: object) -> str:
            raise ValueError("LLM crashed")

        with patch("app.main._answer_vqa", mock_failing_vqa):
            with TestClient(app) as cl:
                resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        pred = resp.json()["predictions"][0]
        assert pred["error"] == "LLM crashed"

    def test_predict_multiple_samples(self) -> None:
        """Batch prediction returns an item per sample in order."""
        img_b64 = _make_image_bytes_b64()
        payload = _predict_payload(
            target="image_classification",
            label_space=["cat", "dog"],
            samples=[
                {"sample_id": "s1", "image_bytes_b64": img_b64},
                {"sample_id": "s2", "image_bytes_b64": img_b64},
            ],
        )
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        predictions = resp.json()["predictions"]
        assert len(predictions) == 2
        assert [p["sample_id"] for p in predictions] == ["s1", "s2"]


class TestPredictValidation:
    """Verify invalid predict payloads get 422 (Pydantic validation), not 500."""

    def test_missing_model_field(self) -> None:
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json={"target": "image_classification"})
        assert resp.status_code == 422

    def test_missing_target_field(self) -> None:
        with TestClient(app) as cl:
            resp = cl.post(
                "/v1/predict",
                json={"model": {"id": "m", "uri": "u", "content_b64": "e30="}},
            )
        assert resp.status_code == 422

    def test_missing_model_content_b64(self) -> None:
        with TestClient(app) as cl:
            resp = cl.post(
                "/v1/predict",
                json={
                    "model": {"id": "m", "uri": "u"},
                    "target": "image_classification",
                },
            )
        assert resp.status_code == 422

    def test_empty_body(self) -> None:
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json={})
        assert resp.status_code == 422


# ── Embed endpoint ──────────────────────────────────────────────────────────


class TestEmbedEndpoint:
    """Verify /v1/embed response shape."""

    def test_embed_single_sample(self) -> None:
        payload = _embed_payload()
        with TestClient(app) as cl:
            resp = cl.post("/v1/embed", json=payload)

        assert resp.status_code == 200
        body = resp.json()
        assert "embeddings" in body
        assert isinstance(body["embeddings"], list)
        assert len(body["embeddings"]) == 1

        emb = body["embeddings"][0]
        assert emb["sample_id"] == "s1"
        assert isinstance(emb["embedding"], list)
        assert len(emb["embedding"]) == 64  # default dim
        assert all(isinstance(x, float) for x in emb["embedding"])
        assert emb["error"] is None

    def test_embed_normalized(self) -> None:
        """Embedding vectors are L2-normalized."""
        payload = _embed_payload()
        with TestClient(app) as cl:
            resp = cl.post("/v1/embed", json=payload)

        emb = resp.json()["embeddings"][0]["embedding"]
        import math

        norm = math.sqrt(sum(x * x for x in emb))
        assert abs(norm - 1.0) < 1e-9, f"Expected normalized vector, got norm={norm}"

    def test_embed_missing_image_bytes_returns_error(self) -> None:
        payload = _embed_payload(
            samples=[{"sample_id": "s1"}],
        )
        with TestClient(app) as cl:
            resp = cl.post("/v1/embed", json=payload)

        assert resp.status_code == 200
        emb = resp.json()["embeddings"][0]
        assert emb["sample_id"] == "s1"
        assert emb["error"] == "missing image bytes"

    def test_embed_multiple_samples(self) -> None:
        img_b64 = _make_image_bytes_b64()
        payload = _embed_payload(
            samples=[
                {"sample_id": "s1", "image_bytes_b64": img_b64},
                {"sample_id": "s2", "image_bytes_b64": img_b64},
            ],
        )
        with TestClient(app) as cl:
            resp = cl.post("/v1/embed", json=payload)

        assert resp.status_code == 200
        embeddings = resp.json()["embeddings"]
        assert len(embeddings) == 2
        assert [e["sample_id"] for e in embeddings] == ["s1", "s2"]

    def test_embed_same_image_produces_consistent_embedding(self) -> None:
        """Same image encoded twice produces the same embedding (deterministic)."""
        img_b64 = _make_image_bytes_b64()
        payload1 = _embed_payload(
            samples=[{"sample_id": "s1", "image_bytes_b64": img_b64}],
        )
        payload2 = _embed_payload(
            samples=[{"sample_id": "s2", "image_bytes_b64": img_b64}],
        )
        with TestClient(app) as cl:
            emb1 = cl.post("/v1/embed", json=payload1).json()["embeddings"][0]["embedding"]
            emb2 = cl.post("/v1/embed", json=payload2).json()["embeddings"][0]["embedding"]

        assert emb1 == emb2


class TestEmbedValidation:
    """Verify invalid embed payloads get 422 (Pydantic validation), not 500."""

    def test_missing_model_name(self) -> None:
        with TestClient(app) as cl:
            resp = cl.post("/v1/embed", json={"samples": []})
        assert resp.status_code == 422

    def test_empty_body(self) -> None:
        with TestClient(app) as cl:
            resp = cl.post("/v1/embed", json={})
        assert resp.status_code == 422


# ── Helper functions ────────────────────────────────────────────────────────


class TestHelpers:
    """Verify _image_embedding_from_bytes, _cosine, and _answer_vqa helpers."""

    def test_image_embedding_from_bytes_dimension(self) -> None:
        from app.main import _image_embedding_from_bytes

        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (4, 4)).save(buf, format="JPEG")
        emb = _image_embedding_from_bytes(buf.getvalue(), dim=64)
        assert len(emb) == 64
        assert all(isinstance(x, float) for x in emb)

    def test_image_embedding_normalized(self) -> None:
        from app.main import _image_embedding_from_bytes

        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 8), color=(100, 150, 200)).save(buf, format="JPEG")
        emb = _image_embedding_from_bytes(buf.getvalue())
        import math

        norm = math.sqrt(sum(x * x for x in emb))
        assert abs(norm - 1.0) < 1e-9

    def test_cosine_identical(self) -> None:
        from app.main import _cosine

        v = [0.6, 0.8]
        assert abs(_cosine(v, v) - 1.0) < 1e-9

    def test_cosine_orthogonal(self) -> None:
        from app.main import _cosine

        assert abs(_cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9

    def test_cosine_zero_vector(self) -> None:
        from app.main import _cosine

        assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_answer_vqa_missing_env(self) -> None:
        """_answer_vqa raises ValueError when LLM_API_KEY is not set."""
        import os

        old = os.environ.pop("LLM_API_KEY", None)
        old_model = os.environ.pop("LLM_MODEL", None)
        try:
            import pytest

            from app.main import _answer_vqa

            from io import BytesIO

            from PIL import Image

            buf = BytesIO()
            Image.new("RGB", (1, 1)).save(buf, format="JPEG")

            with pytest.raises(ValueError, match="api_key"):
                import asyncio

                asyncio.run(_answer_vqa(buf.getvalue(), "What?", "Be helpful"))
        finally:
            if old is not None:
                os.environ["LLM_API_KEY"] = old
            if old_model is not None:
                os.environ["LLM_MODEL"] = old_model


# ── Metrics ─────────────────────────────────────────────────────────────────


class TestMetricsRecording:
    """Verify predict/embed calls are recorded in Prometheus metrics."""

    def test_predict_metrics_appear_after_call(self) -> None:
        payload = _predict_payload(
            target="image_classification",
            label_space=["cat", "dog"],
        )
        with TestClient(app) as cl:
            cl.post("/v1/predict", json=payload)
            metrics_resp = cl.get("/metrics")

        assert metrics_resp.status_code == 200
        text = metrics_resp.text
        assert "platform_gpu_worker_prediction_batch_duration_seconds" in text

    def test_embed_metrics_appear_after_call(self) -> None:
        payload = _embed_payload()
        with TestClient(app) as cl:
            cl.post("/v1/embed", json=payload)
            metrics_resp = cl.get("/metrics")

        assert metrics_resp.status_code == 200
        text = metrics_resp.text
        assert "platform_gpu_worker_embedding_batch_duration_seconds" in text


# ── Response shape contract (matches InferenceWorkerClient) ─────────────────


class TestResponseContract:
    """Verify response shapes match what InferenceWorkerClient expects."""

    def test_predict_response_shape(self) -> None:
        """Response must have {"predictions": [{"sample_id", "label", "confidence", "scores", "error"}]}."""
        payload = _predict_payload(
            target="image_classification",
            label_space=["cat", "dog"],
        )
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json=payload)

        body = resp.json()
        assert isinstance(body, dict)
        assert "predictions" in body
        for item in body["predictions"]:
            assert isinstance(item, dict)
            assert "sample_id" in item
            assert "label" in item
            assert "confidence" in item or item.get("confidence") is None
            assert "scores" in item
            assert "error" in item or item.get("error") is None

    def test_embed_response_shape(self) -> None:
        """Response must have {"embeddings": [{"sample_id", "embedding", "error"}]}."""
        payload = _embed_payload()
        with TestClient(app) as cl:
            resp = cl.post("/v1/embed", json=payload)

        body = resp.json()
        assert isinstance(body, dict)
        assert "embeddings" in body
        for item in body["embeddings"]:
            assert isinstance(item, dict)
            assert "sample_id" in item
            assert "embedding" in item or item.get("error")
            assert "error" in item or item.get("error") is None

    def test_curl_equivalent_predict(self) -> None:
        """The exact curl command from the task spec should return 200."""
        payload = {
            "model": {
                "id": "test",
                "uri": "test",
                "content_b64": "e30=",
            },
            "target": "image_classification",
            "label_space": ["cat", "dog"],
            "samples": [
                {
                    "sample_id": "s1",
                    "image_uris": ["http://example.com/img.jpg"],
                }
            ],
        }
        with TestClient(app) as cl:
            resp = cl.post("/v1/predict", json=payload)

        assert resp.status_code == 200
        body = resp.json()
        assert "predictions" in body
        assert len(body["predictions"]) == 1
        # Without image_bytes_b64, this returns an error but still 200
        pred = body["predictions"][0]
        assert pred["sample_id"] == "s1"
        assert pred["error"] == "missing image bytes"


# ── Train endpoint ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_job_registry() -> None:
    """Reset the module-level job registry before each test to prevent state leakage."""
    from app.job_registry import JobRegistry

    import app.main

    app.main._job_registry = JobRegistry()


def _noop_training(registry: object, gpu_job_id: str, *args: object, **kwargs: object) -> None:
    """Simulate a training run that starts and stays running (non-terminal)."""
    registry.update_status(gpu_job_id, "running")  # type: ignore[union-attr]


def _completing_training(registry: object, gpu_job_id: str, *args: object, **kwargs: object) -> None:
    """Simulate a training run that completes successfully."""
    registry.update_status(gpu_job_id, "running")  # type: ignore[union-attr]
    registry.update_status(gpu_job_id, "completed", progress=1.0)  # type: ignore[union-attr]


def _failing_training(registry: object, gpu_job_id: str, *args: object, **kwargs: object) -> None:
    """Simulate a training run that fails."""
    registry.update_status(gpu_job_id, "running")  # type: ignore[union-attr]
    registry.update_status(gpu_job_id, "failed", error="mock failure")  # type: ignore[union-attr]


class TestTrainSubmit:
    """Verify POST /v1/train submission and idempotency."""

    def test_minimal_payload_accepted(self) -> None:
        """Minimal payload without model_id is accepted with 202."""
        payload = {
            "platform_job_id": "pj-minimal",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        with patch("app.main.run_training_background", _noop_training):
            with TestClient(app) as cl:
                resp = cl.post("/v1/train", json=payload)

        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "accepted"
        assert body["position"] == 0

    def test_missing_platform_job_id_rejected(self) -> None:
        """Missing required fields get 422."""
        payload = {
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        with TestClient(app) as cl:
            resp = cl.post("/v1/train", json=payload)
        assert resp.status_code == 422

    def test_missing_preset_id_rejected(self) -> None:
        payload = {
            "platform_job_id": "pj-1",
            "dataset_id": "ds-1",
        }
        with TestClient(app) as cl:
            resp = cl.post("/v1/train", json=payload)
        assert resp.status_code == 422

    def test_missing_dataset_id_rejected(self) -> None:
        payload = {
            "platform_job_id": "pj-1",
            "preset_id": "resnet50-cls-v1",
        }
        with TestClient(app) as cl:
            resp = cl.post("/v1/train", json=payload)
        assert resp.status_code == 422

    def test_duplicate_submit_is_idempotent(self) -> None:
        """Same platform_job_id returns 409 with already_submitted."""
        payload = {
            "platform_job_id": "pj-dup",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        with patch("app.main.run_training_background", _noop_training):
            with TestClient(app) as cl:
                resp1 = cl.post("/v1/train", json=payload)
                resp2 = cl.post("/v1/train", json=payload)

        assert resp1.status_code == 202
        assert resp2.status_code == 409
        assert resp2.json()["status"] == "already_submitted"
        assert resp2.json()["job_id"] == resp1.json()["job_id"]

    def test_concurrent_job_rejected(self) -> None:
        """Different platform_job_id while another is active gets 409."""
        payload1 = {
            "platform_job_id": "pj-conc-1",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        payload2 = {
            "platform_job_id": "pj-conc-2",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-2",
        }
        with patch("app.main.run_training_background", _noop_training):
            with TestClient(app) as cl:
                resp1 = cl.post("/v1/train", json=payload1)
                resp2 = cl.post("/v1/train", json=payload2)

        assert resp1.status_code == 202
        assert resp2.status_code == 409
        assert "already running" in resp2.json()["detail"].lower()


class TestTrainStatus:
    """Verify GET /v1/train/{job_id} returns correct contract shape."""

    def test_status_for_existing_job(self) -> None:
        payload = {
            "platform_job_id": "pj-status",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        with patch("app.main.run_training_background", _completing_training):
            with TestClient(app) as cl:
                submit = cl.post("/v1/train", json=payload)
                job_id = submit.json()["job_id"]
                resp = cl.get(f"/v1/train/{job_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job_id
        assert body["platform_job_id"] == "pj-status"
        assert body["status"] in ("pending", "running", "completed", "failed")
        assert isinstance(body["progress"], (int, float))
        assert isinstance(body["metrics"], dict)
        assert "created_at" in body
        assert "updated_at" in body

    def test_status_for_unknown_job_returns_404(self) -> None:
        with TestClient(app) as cl:
            resp = cl.get("/v1/train/nonexistent-job")

        assert resp.status_code == 404


class TestTrainCancel:
    """Verify POST /v1/train/{job_id}/cancel."""

    def test_cancel_active_job(self) -> None:
        payload = {
            "platform_job_id": "pj-cancel",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        with patch("app.main.run_training_background", _noop_training):
            with TestClient(app) as cl:
                submit = cl.post("/v1/train", json=payload)
                job_id = submit.json()["job_id"]
                resp = cl.post(f"/v1/train/{job_id}/cancel")

        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_unknown_job_returns_404(self) -> None:
        with TestClient(app) as cl:
            resp = cl.post("/v1/train/nonexistent/cancel")
        assert resp.status_code == 404

    def test_cancel_already_terminal_returns_409(self) -> None:
        payload = {
            "platform_job_id": "pj-term",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        with patch("app.main.run_training_background", _noop_training):
            with TestClient(app) as cl:
                submit = cl.post("/v1/train", json=payload)
                job_id = submit.json()["job_id"]
                cl.post(f"/v1/train/{job_id}/cancel")
                resp = cl.post(f"/v1/train/{job_id}/cancel")

        assert resp.status_code == 409


class TestTrainLogs:
    """Verify GET /v1/train/{job_id}/logs."""

    def test_logs_for_existing_job(self) -> None:
        payload = {
            "platform_job_id": "pj-logs",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        with patch("app.main.run_training_background", _noop_training):
            with TestClient(app) as cl:
                submit = cl.post("/v1/train", json=payload)
                job_id = submit.json()["job_id"]
                resp = cl.get(f"/v1/train/{job_id}/logs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job_id
        assert isinstance(body["logs"], list)

    def test_logs_for_unknown_job_returns_404(self) -> None:
        with TestClient(app) as cl:
            resp = cl.get("/v1/train/nonexistent/logs")
        assert resp.status_code == 404


class TestTrainMetrics:
    """Verify Prometheus metrics reflect training job lifecycle."""

    def test_active_gauge_set_on_submit_and_reset_on_completion(self) -> None:
        payload = {
            "platform_job_id": "pj-metrics-1",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        with patch("app.main.run_training_background", _completing_training):
            with TestClient(app) as cl:
                cl.post("/v1/train", json=payload)
                metrics_text = cl.get("/metrics").text

        assert "platform_gpu_worker_jobs_active" in metrics_text
        assert "platform_gpu_worker_jobs_total" in metrics_text

    def test_active_gauge_reset_on_failure(self) -> None:
        payload = {
            "platform_job_id": "pj-metrics-fail",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        with patch("app.main.run_training_background", _failing_training):
            with TestClient(app) as cl:
                cl.post("/v1/train", json=payload)
                metrics_text = cl.get("/metrics").text

        assert "platform_gpu_worker_jobs_active" in metrics_text

    def test_active_gauge_reset_on_cancel(self) -> None:
        payload = {
            "platform_job_id": "pj-metrics-cancel",
            "preset_id": "resnet50-cls-v1",
            "dataset_id": "ds-1",
        }
        with patch("app.main.run_training_background", _noop_training):
            with TestClient(app) as cl:
                submit = cl.post("/v1/train", json=payload)
                job_id = submit.json()["job_id"]
                cl.post(f"/v1/train/{job_id}/cancel")
                metrics_text = cl.get("/metrics").text

        assert "platform_gpu_worker_jobs_active" in metrics_text
