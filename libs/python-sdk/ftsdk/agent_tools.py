from __future__ import annotations

from typing import Any

from ftsdk.client import FinetuneClient


class AgentTools:
    def __init__(self, client: FinetuneClient) -> None:
        self.client = client

    def list_datasets(self) -> list[dict[str, Any]]:
        return self.client.list_datasets()

    def list_jobs(self) -> list[dict[str, Any]]:
        return self.client.list_jobs()

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        return self.client.get_job_status(job_id)

    def start_training(self, dataset_id: str, preset_id: str) -> dict[str, Any]:
        return self.client.start_training(dataset_id=dataset_id, preset_id=preset_id)
