from __future__ import annotations

from typing import Any

from app.shared.infrastructure.llm.client import OpenAICompatibleLlmClient

_INSTANCE: OpenAICompatibleLlmClient | None = None


def init_llm(cfg: Any) -> None:
    global _INSTANCE

    _INSTANCE = OpenAICompatibleLlmClient(
        base_url=str(cfg.llm.base_url),
        api_key=str(cfg.llm.api_key),
        model=str(cfg.llm.model),
        timeout_seconds=float(cfg.llm.timeout_seconds),
    )


def get_llm() -> OpenAICompatibleLlmClient:
    if _INSTANCE is None:
        raise RuntimeError("LLM infrastructure has not been initialized")
    return _INSTANCE
