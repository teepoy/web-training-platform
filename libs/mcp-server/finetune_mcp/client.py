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

    def create_dataset(self, body: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.post("/datasets", json=body)
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
    # Training jobs
    # ------------------------------------------------------------------

    def list_jobs(self) -> list[dict[str, Any]]:
        resp = self._client.get("/jobs")
        resp.raise_for_status()
        return resp.json()

    def get_job(self, job_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/jobs/{job_id}")
        resp.raise_for_status()
        return resp.json()

    def create_job(self, body: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.post("/jobs", json=body)
        resp.raise_for_status()
        return resp.json()

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        resp = self._client.post(f"/jobs/{job_id}/cancel")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    def list_presets(self) -> list[dict[str, Any]]:
        resp = self._client.get("/presets")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    def list_models(self, dataset_id: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if dataset_id:
            params["dataset_id"] = dataset_id
        resp = self._client.get("/models", params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Predictions
    # ------------------------------------------------------------------

    def list_prediction_jobs(self) -> list[dict[str, Any]]:
        resp = self._client.get("/predictions")
        resp.raise_for_status()
        return resp.json()

    def run_predictions(self, body: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.post("/predictions/run", json=body)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Schedules
    # ------------------------------------------------------------------

    def list_schedules(self) -> list[dict[str, Any]]:
        resp = self._client.get("/schedules")
        resp.raise_for_status()
        return resp.json()

    def create_schedule(self, body: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.post("/schedules", json=body)
        resp.raise_for_status()
        return resp.json()

    def delete_schedule(self, schedule_id: str) -> dict[str, Any]:
        resp = self._client.delete(f"/schedules/{schedule_id}")
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

    # ------------------------------------------------------------------
    # Agent chat
    # ------------------------------------------------------------------

    def agent_chat(
        self,
        message: str,
        session_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a message to the global agent and collect the streamed response.

        The ``POST /agent/chat`` endpoint returns an SSE stream.  This method
        consumes the stream, collects ``agent-message`` content chunks and
        ``agent-action`` summaries, then returns a structured result.
        """
        import json as _json

        body: dict[str, Any] = {"message": message}
        if session_id:
            body["session_id"] = session_id
        if context:
            body["context"] = context

        collected_text: list[str] = []
        actions: list[dict[str, str]] = []

        with self._client.stream("POST", "/agent/chat", json=body) as resp:
            resp.raise_for_status()
            buf = ""
            current_event: str | None = None
            for chunk in resp.iter_text():
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r")

                    if line.startswith("event: "):
                        current_event = line[7:]
                    elif line.startswith("data: ") and current_event:
                        data_str = line[6:]
                        try:
                            data = _json.loads(data_str)
                        except _json.JSONDecodeError:
                            continue
                        if current_event == "agent-message":
                            collected_text.append(data.get("content", ""))
                        elif current_event == "agent-action":
                            actions.append({
                                "tool": data.get("tool", ""),
                                "summary": data.get("summary", ""),
                            })
                        current_event = None
                    elif line == "":
                        current_event = None

        return {
            "response": "".join(collected_text),
            "actions": actions,
            "session_id": session_id,
        }
