"""Bridge tests: PredictContext as canonical executable predictor interface.

These tests verify:

1. PredictContext can be constructed with all fields (direct + defaults)
2. PredictContext can be constructed from flow job data (mimicking predict_job.py)
3. A stub Predictor implementing the Predictor Protocol works with PredictContext
4. Round-trip: PredictContext → predictor predict_single → PredictResult
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import pytest

from platform_runtime.contracts import (
    BatchPredictResult,
    DatasetRef,
    ModelRef,
    PredictContext,
    PredictResult,
    Predictor,
)


# ═══════════════════════════════════════════════════════════════════════
# 1.  Direct construction — all fields
# ═══════════════════════════════════════════════════════════════════════


def test_predict_context_is_dataclass() -> None:
    """PredictContext must be a dataclass (required by runtime serialisation)."""
    assert is_dataclass(PredictContext), "PredictContext must be a dataclass"


def test_predict_context_construct_minimal() -> None:
    """PredictContext can be constructed with only job_id (required field)."""
    ctx = PredictContext(job_id="job-001")
    assert ctx.job_id == "job-001"
    assert ctx.trainer_id == ""
    assert ctx.predict_config == {}
    assert ctx.target == ""
    assert ctx.config_overrides == {}
    assert isinstance(ctx.model_ref, ModelRef)
    assert isinstance(ctx.dataset_ref, DatasetRef)


def test_predict_context_construct_full() -> None:
    """PredictContext accepts all fields explicitly."""
    mr = ModelRef(
        uri="s3://models/resnet.pt",
        framework="pytorch",
        architecture="resnet50",
        num_classes=10,
    )
    dr = DatasetRef(
        dataset_id="ds-001",
        label_space=["cat", "dog"],
        storage_uri_prefix="s3://datasets",
    )
    ctx = PredictContext(
        job_id="job-002",
        trainer_id="resnet50-v1",
        predict_config={"batch_size": 32},
        model_ref=mr,
        dataset_ref=dr,
        target="image_classification",
        config_overrides={"threshold": 0.8},
    )
    assert ctx.job_id == "job-002"
    assert ctx.trainer_id == "resnet50-v1"
    assert ctx.predict_config == {"batch_size": 32}
    assert ctx.model_ref is mr
    assert ctx.dataset_ref is dr
    assert ctx.target == "image_classification"
    assert ctx.config_overrides == {"threshold": 0.8}


# ═══════════════════════════════════════════════════════════════════════
# 2.  Construction from flow job data (predict_job.py pattern)
# ═══════════════════════════════════════════════════════════════════════


def test_predict_context_from_flow_job_data() -> None:
    """Mimic how predict_job.py constructs PredictContext from DB entities.

    The flow reads a Model, Dataset, and PredictionJob from the DB, then
    builds a PredictContext from their primitive fields.  This test
    ensures the contract supports that pattern.
    """
    # ── Simulated DB entities (Pydantic / ORM shapes) ──
    model_entity = {
        "id": "model-abc",
        "uri": "memory://artifacts/model.json",
        "kind": "model",
        "trainer_id": "resnet50-v1",
        "metadata": {
            "framework": "pytorch",
            "architecture": "resnet50",
            "label_space": ["cat", "dog"],
        },
    }
    dataset_entity = {
        "id": "ds-xyz",
        "name": "my-dataset",
        "dataset_type": "image_classification",
        "task_spec": {
            "task_type": "classification",
            "label_space": ["cat", "dog"],
        },
        "storage_mode": "db_full",
    }

    # ── Flow builds PredictContext from these entities ──
    ctx = PredictContext(
        job_id="job-flow-001",
        trainer_id=model_entity.get("trainer_id", ""),
        model_ref=ModelRef(
            uri=model_entity["uri"],
            framework=(model_entity.get("metadata", {}) or {}).get(
                "framework", "pytorch"
            ),
            architecture=(model_entity.get("metadata", {}) or {}).get(
                "architecture", ""
            ),
        ),
        dataset_ref=DatasetRef(
            dataset_id=dataset_entity["id"],
            label_space=dataset_entity.get("task_spec", {}).get("label_space", []),
        ),
        target=dataset_entity.get("dataset_type", "image_classification"),
    )

    assert ctx.job_id == "job-flow-001"
    assert ctx.trainer_id == "resnet50-v1"
    assert ctx.model_ref.uri == "memory://artifacts/model.json"
    assert ctx.model_ref.framework == "pytorch"
    assert ctx.dataset_ref.dataset_id == "ds-xyz"
    assert ctx.dataset_ref.label_space == ["cat", "dog"]
    assert ctx.target == "image_classification"


def test_predict_context_flow_embedding_target() -> None:
    """PredictContext with target='embedding' (used by torch.py predict_embedding)."""
    ctx = PredictContext(
        job_id="job-emb-001",
        trainer_id="torch-prototype-v1",
        model_ref=ModelRef(uri="memory://models/proto.json"),
        dataset_ref=DatasetRef(dataset_id="ds-1"),
        target="embedding",
        config_overrides={"dim": 64},
    )
    assert ctx.target == "embedding"
    assert ctx.config_overrides == {"dim": 64}


# ═══════════════════════════════════════════════════════════════════════
# 3.  Stub predictor — Predictor Protocol contract
# ═══════════════════════════════════════════════════════════════════════


class _StubClassifier:
    """Minimal predictor implementing the Predictor Protocol.

    Follows the same contract used by all 6 real predictors:
    ClassificationPredictor, DetectionPredictor, VqaPredictor,
    ResnetScPredictor, TorchPredictor, ClipPredictor.
    """

    def __init__(self) -> None:
        self._model_loaded = False
        self._labels: list[str] = []

    async def load_model(self, model_ref: ModelRef) -> None:
        self._model_loaded = True
        self._labels = model_ref.metadata.get("label_space", [])

    async def predict_batch(
        self, ctx: PredictContext, samples: list[Any]
    ) -> BatchPredictResult:
        predictions = [await self.predict_single(ctx, s) for s in samples]
        failed = sum(1 for p in predictions if p.metadata.get("error"))
        return BatchPredictResult(
            predictions=predictions,
            total=len(samples),
            successful=len(samples) - failed,
            failed=failed,
        )

    async def predict_single(self, ctx: PredictContext, sample: Any) -> PredictResult:
        sample_id = str(sample.get("sample_id", ""))
        image_bytes = sample.get("image_bytes")
        if image_bytes is None:
            return PredictResult(
                sample_id=sample_id,
                label="",
                metadata={"error": "missing image_bytes"},
            )
        label = self._labels[0] if self._labels else "unknown"
        return PredictResult(
            sample_id=sample_id,
            label=label,
            confidence=0.99,
        )

    async def unload_model(self) -> None:
        self._model_loaded = False
        self._labels = []


def test_stub_satisfies_predictor_protocol() -> None:
    """Verify the stub is runtime_checkable against the Predictor Protocol."""
    stub = _StubClassifier()
    assert isinstance(stub, Predictor), (
        "_StubClassifier must satisfy the Predictor Protocol"
    )


@pytest.mark.asyncio
async def test_predictor_roundtrip_predictcontext_to_predictresult() -> None:
    """Full round-trip: load model → predict_single → PredictResult."""
    predictor = _StubClassifier()

    # Load model with label space
    model_ref = ModelRef(metadata={"label_space": ["cat", "dog"]})
    await predictor.load_model(model_ref)

    # Build context from flow data
    ctx = PredictContext(
        job_id="job-rt-001",
        trainer_id="stub-v1",
        model_ref=model_ref,
        dataset_ref=DatasetRef(
            dataset_id="ds-1",
            label_space=["cat", "dog"],
        ),
    )

    # Predict single sample
    sample = {
        "sample_id": "sample-1",
        "image_bytes": b"fake_png_bytes",
    }
    result = await predictor.predict_single(ctx, sample)

    assert result.sample_id == "sample-1"
    assert result.label == "cat"
    assert result.confidence == 0.99
    assert result.scores == {}


@pytest.mark.asyncio
async def test_predictor_batch_roundtrip() -> None:
    """Batch prediction round-trip: PredictContext → predict_batch → BatchPredictResult."""
    predictor = _StubClassifier()
    model_ref = ModelRef(metadata={"label_space": ["cat", "dog"]})
    await predictor.load_model(model_ref)

    ctx = PredictContext(
        job_id="job-batch-001",
        model_ref=model_ref,
        dataset_ref=DatasetRef(dataset_id="ds-1"),
    )

    samples = [
        {"sample_id": "s1", "image_bytes": b"img1"},
        {"sample_id": "s2", "image_bytes": b"img2"},
        {"sample_id": "s3"},  # missing image_bytes
    ]
    batch_result = await predictor.predict_batch(ctx, samples)

    assert batch_result.total == 3
    assert batch_result.successful == 2
    assert batch_result.failed == 1
    assert len(batch_result.predictions) == 3
    assert batch_result.predictions[0].label == "cat"
    assert batch_result.predictions[0].confidence == 0.99
    assert batch_result.predictions[2].metadata.get("error") == "missing image_bytes"


@pytest.mark.asyncio
async def test_predictor_missing_image_bytes_returns_error_predictresult() -> None:
    """Missing image_bytes in sample returns error PredictResult, not exception."""
    predictor = _StubClassifier()
    model_ref = ModelRef(metadata={"label_space": ["cat"]})
    await predictor.load_model(model_ref)

    ctx = PredictContext(
        job_id="job-err-001",
        model_ref=model_ref,
        dataset_ref=DatasetRef(dataset_id="ds-1"),
    )

    result = await predictor.predict_single(ctx, {"sample_id": "bad-sample"})
    assert result.sample_id == "bad-sample"
    assert result.label == ""
    assert result.metadata.get("error") == "missing image_bytes"


# ═══════════════════════════════════════════════════════════════════════
# 4.  Field immutability (dataclass semantics)
# ═══════════════════════════════════════════════════════════════════════


def test_predictcontext_fields_mutable_after_construction() -> None:
    """PredictContext fields are standard mutable dataclass fields (not frozen).

    This is intentional — flow code often sets fields incrementally
    (e.g. config_overrides['key'] = value).
    """
    ctx = PredictContext(job_id="job-001")
    ctx.config_overrides["threshold"] = 0.5
    assert ctx.config_overrides["threshold"] == 0.5

    ctx.predict_config["batch_size"] = 16
    assert ctx.predict_config["batch_size"] == 16


def test_predictcontext_asdict_roundtrip_keys() -> None:
    """All PredictContext fields appear in dataclasses.asdict."""
    ctx = PredictContext(
        job_id="job-keys-001",
        trainer_id="t1",
        predict_config={"k": "v"},
        model_ref=ModelRef(uri="u"),
        dataset_ref=DatasetRef(dataset_id="d"),
        target="t",
        config_overrides={"o": "v"},
    )
    d = asdict(ctx)
    expected_keys = {
        "job_id",
        "trainer_id",
        "predict_config",
        "model_ref",
        "dataset_ref",
        "target",
        "config_overrides",
    }
    assert set(d.keys()) == expected_keys, (
        f"Missing or extra keys: {set(d.keys()) ^ expected_keys}"
    )
