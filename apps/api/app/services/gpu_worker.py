from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx


class GpuWorkerClientError(Exception):
    """Raised when the GPU worker returns an error or is unreachable."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GpuWorkerUnavailableError(GpuWorkerClientError):
    """Raised when the GPU worker is unreachable after retries."""


class GpuWorkerClient:
    """HTTP client for the GPU worker API (train/predict/embed).

    Follows the same httpx pattern as ``InferenceWorkerClient``.
    Retries on connection/timeout errors with bounded exponential backoff.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        if not base_url:
            raise GpuWorkerClientError("GPU worker base_url is not configured")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds

    # ── Train ────────────────────────────────────────────────────────

    async def submit_train(
        self,
        *,
        platform_job_id: str,
        preset_id: str,
        dataset_id: str,
        model_id: str = "",
        hyperparameters: dict[str, Any] | None = None,
        artifact_prefix: str = "",
    ) -> dict[str, Any]:
        """Submit a training job to the GPU worker.

        Returns the response body on success (202) or idempotent re-submit (409
        with ``status == "already_submitted"``).  Raises GpuWorkerClientError for
        concurrent-job conflicts and other HTTP errors.
        """
        payload: dict[str, Any] = {
            "platform_job_id": platform_job_id,
            "preset_id": preset_id,
            "dataset_id": dataset_id,
            "model_id": model_id,
            "hyperparameters": hyperparameters or {},
            "artifact_prefix": artifact_prefix,
        }
        try:
            return await self._request("POST", "/v1/train", json=payload)
        except GpuWorkerClientError as exc:
            if exc.status_code == 409:
                body = exc.response_body or {}
                if body.get("status") == "already_submitted" and isinstance(body.get("job_id"), str) and body["job_id"]:
                    return body
                detail = body.get("detail", str(exc))
                if body.get("status") == "already_submitted":
                    detail = f"idempotent re-submit response missing valid job_id (got {body.get('job_id')!r})"
                raise GpuWorkerClientError(
                    f"GPU worker rejected training job: {detail}",
                    status_code=409,
                    response_body=body,
                ) from exc
            raise

    async def get_train_status(self, job_id: str) -> dict[str, Any]:
        """Get the status of a training job."""
        try:
            return await self._request("GET", f"/v1/train/{job_id}")
        except GpuWorkerClientError as exc:
            if exc.status_code == 404:
                raise GpuWorkerClientError(
                    f"Training job {job_id} not found on GPU worker",
                ) from exc
            raise

    async def cancel_train(self, job_id: str) -> dict[str, Any]:
        """Cancel a training job."""
        try:
            return await self._request("POST", f"/v1/train/{job_id}/cancel")
        except GpuWorkerClientError as exc:
            if exc.status_code == 404:
                raise GpuWorkerClientError(
                    f"Training job {job_id} not found on GPU worker",
                ) from exc
            if exc.status_code == 409:
                raise GpuWorkerClientError(
                    f"Cannot cancel training job {job_id}: already in terminal state",
                ) from exc
            raise

    async def get_train_logs(self, job_id: str, tail: int = 100) -> dict[str, Any]:
        """Get logs for a training job."""
        try:
            return await self._request("GET", f"/v1/train/{job_id}/logs", params={"tail": tail})
        except GpuWorkerClientError as exc:
            if exc.status_code == 404:
                raise GpuWorkerClientError(
                    f"Training job {job_id} not found on GPU worker",
                ) from exc
            raise

    # ── Predict (compatibility — identical payload to InferenceWorkerClient) ──

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
        payload: dict[str, Any] = {
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
        body = await self._request("POST", "/v1/predict", json=payload)
        predictions = body.get("predictions", [])
        if not isinstance(predictions, list):
            raise ValueError("GPU worker returned invalid predictions payload")
        return predictions

    # ── Embed (compatibility — identical payload to InferenceWorkerClient) ────

    async def embed_batch(
        self,
        *,
        model_name: str,
        samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model_name": model_name,
            "samples": [self._encode_sample(sample) for sample in samples],
        }
        body = await self._request("POST", "/v1/embed", json=payload)
        embeddings = body.get("embeddings", [])
        if not isinstance(embeddings, list):
            raise ValueError("GPU worker returned invalid embedding payload")
        return embeddings

    # ── Health ───────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """Check GPU worker health."""
        return await self._request("GET", "/health")

    # ── Internal ──────────────────────────────────────────────────────

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

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with bounded retry/backoff.

        Retries only on connection/timeout/remote-protocol errors (not on
        HTTP-level errors like 4xx/5xx).  HTTP-level errors are always wrapped
        as GpuWorkerClientError so callers never see raw httpx exceptions.
        """
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    if method == "GET":
                        response = await client.get(url, params=params)
                    elif method == "POST":
                        response = await client.post(url, json=json, params=params)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")
                    response.raise_for_status()
                    return response.json()
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                if attempt == self._max_retries:
                    raise GpuWorkerUnavailableError(
                        f"GPU worker unreachable at {self._base_url}{path}: {exc}"
                    ) from exc
                delay = self._retry_delay_seconds * (2**attempt)
                await asyncio.sleep(delay)
            except httpx.HTTPStatusError as exc:
                try:
                    body: dict[str, Any] | None = exc.response.json()
                except Exception:
                    body = None
                raise GpuWorkerClientError(
                    f"GPU worker returned HTTP {exc.response.status_code}: {exc.response.text[:500]}",
                    status_code=exc.response.status_code,
                    response_body=body,
                ) from exc

        # Should never reach here — satisfy type checker
        raise GpuWorkerUnavailableError(
            f"GPU worker unreachable at {self._base_url} after {self._max_retries} retries"
        ) from last_exc
