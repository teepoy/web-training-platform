from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.domain.models import Sample
from app.domain.models import Dataset, Model, TaskSpec
from app.domain.types import DatasetType, TaskType
from app.main import app, container
from app.presets.registry import PresetRegistry
from app.presets.runtime import DatasetRef, ModelRef, PredictContext, TrainContext
from app.runtime.dspy import DspyVqaPredictor, DspyVqaTrainer
from app.services.prediction_service import PredictionService
from app.storage.minio_storage import InMemoryArtifactStorage


class _FakeLlm:
    async def answer_vqa(self, *, image_bytes: bytes, question: str, system_prompt: str) -> str:
        return f"answer:{question}"


class _FakePredictor:
    def __init__(self) -> None:
        self.last_question = ""

    async def predict_single(self, ctx, sample):
        self.last_question = str(sample.get("question", ""))
        from app.presets.runtime import PredictResult

        return PredictResult(sample_id=str(sample.get("sample_id", "")), label="ok")


class _RepoStub:
    async def get_model(self, model_id: str, org_id: str):
        return Model(
            id=model_id,
            uri="memory://artifacts/model.json",
            kind="model",
            job_id="job-1",
            dataset_id="ds-1",
            preset_name="dspy-vqa-v1",
        )

    async def get_dataset(self, dataset_id: str, org_id: str | None = None):
        return Dataset(
            id=dataset_id,
            name="cls-ds",
            dataset_type=DatasetType.IMAGE_CLASSIFICATION,
            task_spec=TaskSpec(task_type=TaskType.CLASSIFICATION, label_space=["cat", "dog"]),
            ls_project_id="1",
        )


def _load_vqa_preset():
    registry = PresetRegistry("presets", strict=True)
    registry.load()
    preset = registry.get_preset("dspy-vqa-v1")
    assert preset is not None
    return preset


def test_create_vqa_dataset_uses_vqa_label_config() -> None:
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/datasets",
            json={
                "name": "vqa-ds",
                "task_spec": {"task_type": "vqa", "label_space": []},
            },
        )
        assert r.status_code == 200

        ls_client = container.label_studio_client()
        assert ls_client.create_project.await_count == 1
        args, _ = ls_client.create_project.call_args
        label_config = args[1]
        assert "<TextArea name=\"answer\"" in label_config
        assert "value=\"$question\"" in label_config


def test_import_vqa_jsonl_samples_endpoint() -> None:
    with TestClient(app) as c:
        ds = c.post(
            "/api/v1/datasets",
            json={"name": "vqa-import", "task_spec": {"task_type": "vqa", "label_space": []}},
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]

        body = (
            '{"image_uri":"memory://samples/vqa/1.jpg","question":"What color is the car?","answer":"red"}\n'
            '{"image_uri":"memory://samples/vqa/2.jpg","question":"How many people?","answer":"two"}\n'
        ).encode("utf-8")
        r = c.post(
            f"/api/v1/datasets/{dataset_id}/samples/import-vqa",
            files={"file": ("vqa.jsonl", body, "application/json")},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["imported"] == 2
        assert payload["failed"] == 0

        listed = c.get(f"/api/v1/datasets/{dataset_id}/samples")
        assert listed.status_code == 200
        assert listed.json()["total"] == 2


def test_import_vqa_jsonl_rejects_non_vqa_dataset() -> None:
    with TestClient(app) as c:
        ds = c.post(
            "/api/v1/datasets",
            json={
                "name": "cls-ds",
                "task_spec": {"task_type": "classification", "label_space": ["cat", "dog"]},
            },
        )
        assert ds.status_code == 200
        dataset_id = ds.json()["id"]
        r = c.post(
            f"/api/v1/datasets/{dataset_id}/samples/import-vqa",
            files={"file": ("vqa.jsonl", b"{}\n", "application/json")},
        )
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_dspy_vqa_trainer_persists_optimized_program_bytes() -> None:
    preset = _load_vqa_preset()
    storage = InMemoryArtifactStorage()
    trainer = DspyVqaTrainer(artifact_storage=storage, llm_client=_FakeLlm())

    ctx = TrainContext(
        job_id="job-vqa-1",
        preset=preset,
        model_ref=ModelRef(framework="dspy", architecture="vqa-program", base_model="gpt-4o-mini"),
        dataset_ref=DatasetRef(
            dataset_id="ds-vqa",
            metadata={
                "records": [
                    {
                        "sample_id": "s1",
                        "image_uri": "memory://samples/1.jpg",
                        "question": "What color is the car?",
                        "answer": "red",
                    }
                ]
            },
        ),
    )

    result = await trainer.train(ctx)
    assert result.model_uri.startswith("memory://")
    raw = await storage.get_bytes(result.model_uri)
    program = json.loads(raw.decode("utf-8"))
    assert program["program_type"] == "dspy-vqa"
    assert len(program["fewshot_examples"]) == 1
    assert program["fewshot_examples"][0]["answer"] == "red"


@pytest.mark.asyncio
async def test_dspy_vqa_predictor_loads_program_and_answers() -> None:
    preset = _load_vqa_preset()
    storage = InMemoryArtifactStorage()
    model_uri = await storage.put_bytes(
        object_name="artifacts/job-vqa-2/optimized_program.json",
        data=json.dumps(
            {
                "program_type": "dspy-vqa",
                "instruction": "Answer precisely",
                "fewshot_examples": [],
            }
        ).encode("utf-8"),
        content_type="application/json",
    )
    predictor = DspyVqaPredictor(artifact_storage=storage, llm_client=_FakeLlm())
    await predictor.load_model(ModelRef(uri=model_uri))

    pred = await predictor.predict_single(
        PredictContext(
            job_id="job-vqa-2",
            preset=preset,
            model_ref=ModelRef(uri=model_uri),
            dataset_ref=DatasetRef(dataset_id="ds-vqa"),
            target="vqa",
        ),
        {
            "sample_id": "s2",
            "image_bytes": b"fake-image",
            "question": "What is on the table?",
        },
    )
    assert pred.sample_id == "s2"
    assert pred.label == "answer:What is on the table?"


@pytest.mark.asyncio
async def test_prediction_prompt_override_for_vqa() -> None:
    svc = PredictionService(
        repository=None,
        artifact_storage=InMemoryArtifactStorage(),
        config=SimpleNamespace(label_studio=SimpleNamespace(url="", api_key="")),
    )
    sample = Sample(
        id="s3",
        dataset_id="ds-vqa",
        image_uris=["data:image/jpeg;base64,ZmFrZQ=="],
        metadata={"question": "original question"},
        ls_task_id=1,
    )
    fake_predictor = _FakePredictor()
    fake_ls = SimpleNamespace(create_prediction=lambda **_: {"id": 1})
    async def _create_prediction(*args, **kwargs):
        return {"id": 1}
    fake_ls.create_prediction = _create_prediction

    preset = _load_vqa_preset()
    ctx = PredictContext(
        job_id="job-vqa-3",
        preset=preset,
        model_ref=ModelRef(uri="memory://model"),
        dataset_ref=DatasetRef(dataset_id="ds-vqa"),
        target="vqa",
    )
    result = await svc._predict_sample(
        sample=sample,
        predictor=fake_predictor,
        predict_ctx=ctx,
        model_version="model-vqa",
        ls_client=fake_ls,
        target="vqa",
        prompt="override question",
    )
    assert result.error is None
    assert fake_predictor.last_question == "override question"


@pytest.mark.asyncio
async def test_prediction_target_vqa_requires_vqa_dataset() -> None:
    svc = PredictionService(
        repository=_RepoStub(),
        artifact_storage=InMemoryArtifactStorage(),
        config=SimpleNamespace(label_studio=SimpleNamespace(url="", api_key="")),
    )
    with pytest.raises(ValueError, match="target 'vqa' requires dataset task_type 'vqa'"):
        await svc.run_prediction(
            model_id="model-1",
            dataset_id="ds-1",
            org_id="org-1",
            target="vqa",
        )
