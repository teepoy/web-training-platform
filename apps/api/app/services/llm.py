"""LLM service layer backed by litellm.

Provides two public interfaces:

1. ``OpenAICompatibleLlmClient`` — multimodal VQA client (used by prediction
   runtime and DI container).
2. ``call_llm`` — async helper for agent tool-calling loops (used by
   ``ClassifyAgent`` and ``GlobalAgent``).

litellm handles provider routing via the model string:
  - ``gpt-4o-mini``              → OpenAI
  - ``qwen/qwen-max``            → Alibaba Qwen
  - ``gemini/gemini-2.0-flash``  → Google Gemini
  - ``anthropic/claude-sonnet``  → Anthropic

When ``api_base`` is set, litellm treats it as an OpenAI-compatible custom
endpoint (same behaviour as the previous raw-httpx implementation).
"""
from __future__ import annotations

import base64
import logging
from typing import Any

import litellm

_logger = logging.getLogger(__name__)

# Suppress litellm's noisy default logging (it logs full payloads at INFO)
litellm.suppress_debug_info = True


class LlmClientError(Exception):
    """Raised when the configured LLM provider returns an error."""


class OpenAICompatibleLlmClient:
    """Multimodal LLM client for VQA generation, backed by litellm."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else ""
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def answer_vqa(
        self,
        *,
        image_bytes: bytes,
        question: str,
        system_prompt: str,
    ) -> str:
        if not self._api_key:
            raise LlmClientError("LLM api_key is not configured")
        if not self._model:
            raise LlmClientError("LLM model is not configured")

        data_uri = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.2,
            "timeout": self._timeout_seconds,
            "api_key": self._api_key,
        }
        if self._base_url:
            kwargs["api_base"] = self._base_url

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise LlmClientError(f"LLM request failed: {exc}") from exc

        choices = response.choices  # type: ignore[union-attr]
        if not choices:
            raise LlmClientError("LLM response has no choices")
        content = choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise LlmClientError("LLM response content is empty")
        return content.strip()


# ---------------------------------------------------------------------------
# Agent helper — used by ClassifyAgent and GlobalAgent
# ---------------------------------------------------------------------------


async def call_llm(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
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

    response = await litellm.acompletion(**kwargs)

    # Convert to plain dict so callers can use it the same way as before
    return response.model_dump()  # type: ignore[union-attr]
