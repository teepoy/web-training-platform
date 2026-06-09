from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from libs.ml.domain import TrainContext, TrainResult
from libs.ml.protocols import ArtifactStorage, LlmClient


def _get_logger() -> logging.Logger:
    """Return a standard Python logger."""
    return logging.getLogger(__name__)


class VqaTrainer:
    """DSPy-based VQA program optimizer (few-shot example selection)."""

    def __init__(
        self,
        artifact_storage: ArtifactStorage,
        llm_client: LlmClient | None = None,
    ) -> None:
        self._artifact_storage = artifact_storage
        self._llm_client = llm_client

    async def train(self, ctx: TrainContext) -> TrainResult:
        logger = _get_logger()
        records = list(ctx.dataset_ref.metadata.get("records", []))
        if not records:
            raise ValueError("VQA training requires dataset records from adapter")

        max_demos = int(ctx.train_config.get("max_demos", 8))
        selected: list[dict[str, str]] = []
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
            raise ValueError(
                "VQA training needs at least one record with question, answer, and image"
            )

        instruction = str(
            ctx.train_config.get(
                "instruction",
                "Answer the user question based only on visual evidence in the image. Be concise and factual.",
            )
        )
        optimized_program: dict[str, Any] = {
            "program_type": "dspy-vqa",
            "version": "1.0.0",
            "created_at": datetime.now(UTC).isoformat(),
            "base_model": ctx.train_config.get("base_model", "gpt-4o-mini"),
            "instruction": instruction,
            "fewshot_examples": selected,
            "optimizer": str(ctx.train_config.get("optimizer", "bootstrap_fewshot")),
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

        logger.info(
            "DSPy VQA optimization finished job_id=%s examples=%s",
            ctx.job_id,
            len(selected),
        )

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
