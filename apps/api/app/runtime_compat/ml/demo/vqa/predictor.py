from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.runtime_compat.ml.demo.domain import (
    BatchPredictResult,
    PredictContext,
    PredictResult,
)
from app.runtime_compat.ml.demo.protocols import ArtifactStorage, LlmClient

_logger = logging.getLogger(__name__)


class VqaPredictor:
    """DSPy VQA program-based prediction via LLM inference.

    Predictions produce free-text answers (textarea semantics), never
    classification choices.
    """

    def __init__(
        self, artifact_storage: ArtifactStorage, llm_client: LlmClient
    ) -> None:
        self._artifact_storage = artifact_storage
        self._llm_client = llm_client
        self._program: dict[str, Any] | None = None

    async def load_model(self, model_ref: Any) -> None:
        if not hasattr(model_ref, "uri") or not model_ref.uri:
            raise ValueError("VQA model uri is empty")
        raw = await self._artifact_storage.get_bytes(model_ref.uri)
        program = json.loads(raw.decode("utf-8"))
        if not isinstance(program, dict) or "instruction" not in program:
            raise ValueError("Invalid optimized VQA program")
        self._program = program

    async def predict_batch(
        self, ctx: PredictContext, samples: list[Any]
    ) -> BatchPredictResult:
        _logger.info("VQA predict_batch started — %d samples", len(samples))
        t_start = time.monotonic()
        predictions = [await self.predict_single(ctx, sample) for sample in samples]
        failed = sum(1 for p in predictions if p.metadata.get("error"))
        elapsed = time.monotonic() - t_start
        _logger.info(
            "VQA predict_batch finished — %d/%d successful (%.1f samples/s)",
            len(samples) - failed,
            len(samples),
            len(samples) / elapsed if elapsed > 0 else 0,
        )
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
            return PredictResult(
                sample_id=sample_id, label="", metadata={"error": "missing image bytes"}
            )
        if not question:
            return PredictResult(
                sample_id=sample_id, label="", metadata={"error": "missing question"}
            )
        if self._llm_client is None:
            return PredictResult(
                sample_id=sample_id,
                label="",
                metadata={"error": "llm client not configured"},
            )

        try:
            answer = await self._llm_client.answer_vqa(
                image_bytes=image_bytes,
                question=question,
                system_prompt=str(self._program.get("instruction", "")),
            )
        except Exception as exc:
            return PredictResult(
                sample_id=sample_id,
                label="",
                metadata={"error": f"vqa inference failed: {exc}"},
            )

        return PredictResult(
            sample_id=sample_id,
            label=answer,
            confidence=None,
            metadata={"question": question},
        )

    async def unload_model(self) -> None:
        self._program = None
