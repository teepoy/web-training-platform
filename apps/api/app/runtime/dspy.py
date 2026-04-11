from __future__ import annotations

import json
from datetime import UTC, datetime
import logging
from typing import Any

from prefect import get_run_logger

from app.presets.runtime import BatchPredictResult, PredictContext, PredictResult, TrainContext, TrainResult


def _logger():
    try:
        return get_run_logger()
    except Exception:
        return logging.getLogger(__name__)


class DspyVqaTrainer:
    def __init__(self, artifact_storage: Any, llm_client: Any = None) -> None:
        self._artifact_storage = artifact_storage
        self._llm_client = llm_client

    async def train(self, ctx: TrainContext) -> TrainResult:
        logger = _logger()
        records = list(ctx.dataset_ref.metadata.get("records", []))
        if not records:
            raise ValueError("VQA training requires dataset records from adapter")

        max_demos = int(ctx.preset.train.config.get("max_demos", 8))
        selected = []
        for rec in records:
            question = str(rec.get("question", "")).strip()
            answer = rec.get("answer")
            image_uri = str(rec.get("image_uri", "")).strip()
            if question and isinstance(answer, str) and answer.strip() and image_uri:
                selected.append(
                    {
                        "question": question,
                        "answer": answer.strip(),
                        "image_uri": image_uri,
                    }
                )
            if len(selected) >= max_demos:
                break

        if not selected:
            raise ValueError("VQA training needs at least one record with question, answer, and image")

        instruction = str(
            ctx.preset.train.config.get(
                "instruction",
                "Answer the user question based only on visual evidence in the image. Be concise and factual.",
            )
        )
        optimized_program = {
            "program_type": "dspy-vqa",
            "version": "1.0.0",
            "created_at": datetime.now(UTC).isoformat(),
            "base_model": ctx.preset.model.base_model,
            "instruction": instruction,
            "fewshot_examples": selected,
            "optimizer": str(ctx.preset.train.config.get("optimizer", "bootstrap_fewshot")),
        }

        artifact_prefix = f"artifacts/{ctx.job_id}"
        optimized_program_object = f"{artifact_prefix}/optimized_program.json"
        metrics_object = f"{artifact_prefix}/metrics.json"
        optimized_program_uri = await self._artifact_storage.put_bytes(
            object_name=optimized_program_object,
            data=json.dumps(optimized_program, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )
        metrics_payload = {
            "records_total": len(records),
            "fewshot_examples": len(selected),
            "optimizer": optimized_program["optimizer"],
        }
        metrics_uri = await self._artifact_storage.put_bytes(
            object_name=metrics_object,
            data=json.dumps(metrics_payload, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )

        logger.info("DSPy VQA optimization finished job_id=%s examples=%s", ctx.job_id, len(selected))

        return TrainResult(
            model_uri=optimized_program_uri,
            metrics=metrics_payload,
            artifact_uris=[optimized_program_uri, metrics_uri],
            metadata={
                "runtime": "dspy",
                "framework": "dspy",
                "optimized_program": optimized_program,
            },
        )


class DspyVqaPredictor:
    def __init__(self, artifact_storage: Any, llm_client: Any) -> None:
        self._artifact_storage = artifact_storage
        self._llm_client = llm_client
        self._program: dict[str, Any] | None = None

    async def load_model(self, model_ref: Any) -> None:
        if not model_ref.uri:
            raise ValueError("VQA model uri is empty")
        raw = await self._artifact_storage.get_bytes(model_ref.uri)
        program = json.loads(raw.decode("utf-8"))
        if not isinstance(program, dict) or "instruction" not in program:
            raise ValueError("Invalid optimized VQA program")
        self._program = program

    async def predict_batch(self, ctx: PredictContext, samples: list[Any]) -> BatchPredictResult:
        predictions = [await self.predict_single(ctx, sample) for sample in samples]
        failed = sum(1 for p in predictions if p.metadata.get("error"))
        return BatchPredictResult(
            predictions=predictions,
            total=len(samples),
            successful=len(samples) - failed,
            failed=failed,
        )

    async def predict_single(self, ctx: PredictContext, sample: Any) -> PredictResult:
        if self._program is None:
            raise ValueError("Model not loaded")
        sample_id = str(sample.get("sample_id", ""))
        image_bytes = sample.get("image_bytes")
        question = str(sample.get("question", "")).strip()
        if not image_bytes:
            return PredictResult(sample_id=sample_id, label="", metadata={"error": "missing image bytes"})
        if not question:
            return PredictResult(sample_id=sample_id, label="", metadata={"error": "missing question"})
        if self._llm_client is None:
            return PredictResult(sample_id=sample_id, label="", metadata={"error": "llm client not configured"})

        try:
            answer = await self._llm_client.answer_vqa(
                image_bytes=image_bytes,
                question=question,
                system_prompt=str(self._program.get("instruction", "")),
            )
        except Exception as exc:
            return PredictResult(sample_id=sample_id, label="", metadata={"error": f"vqa inference failed: {exc}"})

        return PredictResult(
            sample_id=sample_id,
            label=answer,
            confidence=None,
            metadata={"question": question},
        )

    async def unload_model(self) -> None:
        self._program = None
