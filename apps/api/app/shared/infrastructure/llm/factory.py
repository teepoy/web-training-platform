from __future__ import annotations

from app.core.config import load_config
from app.shared.infrastructure.llm.client import OpenAICompatibleLlmClient


def build_llm_client() -> OpenAICompatibleLlmClient:
    """Build an :class:`OpenAICompatibleLlmClient` from the current config profile."""
    cfg = load_config()
    return OpenAICompatibleLlmClient(
        base_url=str(cfg.llm.base_url),
        api_key=str(cfg.llm.api_key),
        model=str(cfg.llm.model),
        timeout_seconds=float(cfg.llm.timeout_seconds),
    )
