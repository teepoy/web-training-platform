from __future__ import annotations

import httpx


class DatasetLoader:
    def __init__(self, client: httpx.Client, dataset_id: str) -> None:
        self._client = client
        self._dataset_id = dataset_id

    def __call__(self, items: list[dict]) -> int:
        r = self._client.post(
            f"/api/v1/datasets/{self._dataset_id}/samples/import",
            json={"items": items},
        )
        if r.status_code == 200:
            return int(r.json().get("imported", 0))
        print(f"    WARN: import batch failed: {r.status_code} {r.text[:120]}")
        return 0
