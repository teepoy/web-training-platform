from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient


class SeedRunner:
    """Create datasets and upload samples via FastAPI TestClient.

    Auth and Label Studio are already mocked by conftest.py autouse fixtures,
    so this runner works without any setup.
    """

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def create_dataset(
        self,
        name: str,
        dataset_type: str,
        task_spec: dict,
    ) -> str:
        """Create a dataset (idempotent). Returns dataset_id."""
        r = self._client.get("/api/v1/datasets")
        existing = r.json() if r.status_code == 200 else []
        for ds in existing:
            if ds.get("name") == name:
                return str(ds["id"])

        r = self._client.post(
            "/api/v1/datasets",
            json={
                "name": name,
                "dataset_type": dataset_type,
                "task_spec": task_spec,
            },
        )
        assert r.status_code in (200, 201), (
            f"create_dataset failed: {r.status_code} {r.text}"
        )
        return str(r.json()["id"])

    def upload_samples(
        self,
        dataset_id: str,
        total: int,
        item_builder: Callable[[int], dict],
        batch_size: int = 5000,
    ) -> int:
        """Upload samples in batches. Returns count created."""
        created = 0
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch = [item_builder(idx) for idx in range(start, end)]
            r = self._client.post(
                f"/api/v1/datasets/{dataset_id}/samples/import",
                json={"items": batch},
            )
            if r.status_code == 200:
                imported = int(r.json().get("imported", 0))
                created += imported
            print(f"  Uploaded {created}/{total} samples ...")
        return created

    def get_summary(self, dataset_id: str) -> dict:
        """Return dataset info dict."""
        r = self._client.get(f"/api/v1/datasets/{dataset_id}")
        assert r.status_code == 200, f"get_summary failed: {r.status_code} {r.text}"
        return r.json()
