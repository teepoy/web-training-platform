"""LLM service layer backed by litellm.

Provides the ``call_llm`` async helper for agent tool-calling loops used by
``ClassifyAgent`` and ``GlobalAgent``.

litellm handles provider routing via the model string:
  - ``gpt-4o-mini``              → OpenAI
  - ``qwen/qwen-max``            → Alibaba Qwen
  - ``gemini/gemini-2.0-flash``  → Google Gemini
  - ``anthropic/claude-sonnet``  → Anthropic

When ``api_base`` is set, litellm treats it as an OpenAI-compatible custom
endpoint (same behaviour as the previous raw-httpx implementation).
"""

from __future__ import annotations

import logging
from typing import Any

import litellm
from litellm.types.llms.openai import AllMessageValues

_logger = logging.getLogger(__name__)

# Suppress litellm's noisy default logging (it logs full payloads at INFO)
setattr(litellm, "suppress_debug_info", True)


# ---------------------------------------------------------------------------
# Agent helper — used by ClassifyAgent and GlobalAgent
# ---------------------------------------------------------------------------


async def call_llm(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    messages: list[AllMessageValues],
    tools: list[dict[str, Any]],
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Call an LLM via litellm with optional tool definitions.

    Returns the raw response as a dict (OpenAI-compatible format) so callers
    can inspect ``choices[0].message.tool_calls`` etc.
    """
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": full_messages,
        "temperature": 0.3,
        "timeout": timeout,
        "api_key": api_key,
    }
    if base_url:
        kwargs["api_base"] = base_url
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response: Any = await litellm.acompletion(**kwargs)

    # Convert to plain dict so callers can use it the same way as before
    return response.model_dump()
