from __future__ import annotations

import base64

import httpx


class LlmClientError(Exception):
    """Raised when the configured LLM provider returns an error."""


class OpenAICompatibleLlmClient:
    """OpenAI-compatible multimodal client for VQA generation."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
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
        if not self._base_url:
            raise LlmClientError("LLM base_url is not configured")
        if not self._api_key:
            raise LlmClientError("LLM api_key is not configured")
        if not self._model:
            raise LlmClientError("LLM model is not configured")
        data_uri = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            raise LlmClientError(f"LLM request failed ({resp.status_code}): {resp.text}")
        body = resp.json()
        choices = body.get("choices", [])
        if not choices:
            raise LlmClientError("LLM response has no choices")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LlmClientError("LLM response content is empty")
        return content.strip()
