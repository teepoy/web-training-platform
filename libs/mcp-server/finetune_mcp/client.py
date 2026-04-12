"""HTTP client wrapper for the finetune platform API."""
from __future__ import annotations

from typing import Any

import httpx

from finetune_mcp.config import McpConfig


class PlatformClient:
    """Thin sync wrapper around the finetune platform API."""

    def __init__(self, config: McpConfig) -> None:
        self._base = config.api_base_url.rstrip("/")
        headers: dict[str, str] = {}
        if config.api_token:
            headers["Authorization"] = f"Bearer {config.api_token}"
        if config.default_org_id:
            headers["X-Organization-ID"] = config.default_org_id
        self._client = httpx.Client(
            base_url=self._base,
            headers=headers,
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Datasets
    # ------------------------------------------------------------------

    def list_datasets(self) -> list[dict[str, Any]]:
        resp = self._client.get("/datasets")
        resp.raise_for_status()
        return resp.json()

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/datasets/{dataset_id}")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Data queries
    # ------------------------------------------------------------------

    def query_data(
        self,
        dataset_id: str,
        query_type: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"query_type": query_type}
        if params:
            body["params"] = params
        resp = self._client.post(f"/datasets/{dataset_id}/query", json=body)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Surface state
    # ------------------------------------------------------------------

    def get_surface_state(
        self, session_id: str, surface_id: str
    ) -> dict[str, Any]:
        resp = self._client.get(f"/sessions/{session_id}/surfaces/{surface_id}")
        resp.raise_for_status()
        return resp.json()

    def set_panel(
        self,
        session_id: str,
        surface_id: str,
        panel: dict[str, Any],
    ) -> dict[str, Any]:
        resp = self._client.post(
            f"/sessions/{session_id}/surfaces/{surface_id}/panels",
            json={"panel": panel},
        )
        resp.raise_for_status()
        return resp.json()

    def remove_panel(
        self, session_id: str, surface_id: str, panel_id: str
    ) -> dict[str, Any]:
        resp = self._client.delete(
            f"/sessions/{session_id}/surfaces/{surface_id}/panels/{panel_id}"
        )
        resp.raise_for_status()
        return resp.json()

    def export_surface(
        self, session_id: str, surface_id: str
    ) -> dict[str, Any]:
        resp = self._client.get(
            f"/sessions/{session_id}/surfaces/{surface_id}/export"
        )
        resp.raise_for_status()
        return resp.json()

    def import_surface(
        self, session_id: str, surface_id: str, document: dict[str, Any]
    ) -> dict[str, Any]:
        resp = self._client.post(
            f"/sessions/{session_id}/surfaces/{surface_id}/import",
            json=document,
        )
        resp.raise_for_status()
        return resp.json()
