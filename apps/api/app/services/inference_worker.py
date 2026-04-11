from __future__ import annotations

import base64
from typing import Any

import httpx


class InferenceWorkerClient:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def predict_batch(
        self,
        *,
        model_id: str,
        model_uri: str,
        model_format: str | None,
        model_metadata: dict[str, Any],
        model_bytes: bytes,
        target: str,
        label_space: list[str],
        samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        payload = {
            "model": {
                "id": model_id,
                "uri": model_uri,
                "format": model_format,
                "metadata": model_metadata,
                "content_b64": base64.b64encode(model_bytes).decode("ascii"),
            },
            "target": target,
            "label_space": label_space,
            "samples": [self._encode_sample(sample) for sample in samples],
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(f"{self._base_url}/v1/predict", json=payload)
            response.raise_for_status()
            body = response.json()
        predictions = body.get("predictions", [])
        if not isinstance(predictions, list):
            raise ValueError("Inference worker returned invalid predictions payload")
        return predictions

    async def embed_batch(
        self,
        *,
        model_name: str,
        samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        payload = {
            "model_name": model_name,
            "samples": [self._encode_sample(sample) for sample in samples],
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(f"{self._base_url}/v1/embed", json=payload)
            response.raise_for_status()
            body = response.json()
        embeddings = body.get("embeddings", [])
        if not isinstance(embeddings, list):
            raise ValueError("Inference worker returned invalid embedding payload")
        return embeddings

    def _encode_sample(self, sample: dict[str, Any]) -> dict[str, Any]:
        image_bytes = sample.get("image_bytes")
        return {
            "sample_id": sample.get("sample_id", ""),
            "image_bytes_b64": None if image_bytes is None else base64.b64encode(image_bytes).decode("ascii"),
            "metadata": sample.get("metadata", {}),
            "image_uris": sample.get("image_uris", []),
            "question": sample.get("question", ""),
            "text": sample.get("text"),
        }
