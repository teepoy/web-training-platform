from __future__ import annotations

from typing import Any

import httpx


class FinetuneClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        token: str | None = None,
        org_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.org_id = org_id

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.org_id:
            headers["X-Organization-ID"] = self.org_id
        return headers

    def _request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> Any:
        with httpx.Client(timeout=15.0) as client:
            resp = client.request(
                method=method,
                url=f"{self.base_url}{path}",
                headers=self._headers(),
                json=json_body,
            )
            resp.raise_for_status()
            return resp.json()

    def list_datasets(self) -> list[dict[str, Any]]:
        return self._request("GET", "/datasets")

    def list_jobs(self) -> list[dict[str, Any]]:
        return self._request("GET", "/training-jobs")

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/training-jobs/{job_id}")

    def start_training(self, dataset_id: str, preset_id: str) -> dict[str, Any]:
        return self._request("POST", "/training-jobs", {"dataset_id": dataset_id, "preset_id": preset_id})
