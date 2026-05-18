from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from seedmaker import SeedConfig


class TestSeedRunner:
    """Thin adapter that mirrors ``SeedRunner``'s API but works with ``TestClient``.

    Skips auth, user registration, and API readiness checks — the test's
    ``_mock_auth_deps`` autouse fixture handles all of that.
    """

    __test__ = False  # Not a pytest test class

    def __init__(self, client: TestClient, config: SeedConfig) -> None:
        self._client = client
        self._config = config
        self._dataset_id: str | None = None
        self._sample_count: int = 0

    @property
    def dataset_id(self) -> str | None:
        return self._dataset_id

    @property
    def sample_count(self) -> int:
        return self._sample_count

    # -----------------------------------------------------------------------
    # Dataset management
    # -----------------------------------------------------------------------

    def ensure_dataset(self) -> str:
        """Create the dataset if it does not already exist.

        Returns the dataset id.
        """
        r = self._client.get("/api/v1/datasets")
        if r.status_code == 200:
            existing = r.json()
            for ds in existing:
                if ds.get("name") == self._config.dataset_name:
                    self._dataset_id = str(ds["id"])
                    return self._dataset_id

        payload: dict[str, Any] = {
            "name": self._config.dataset_name,
            "dataset_type": self._config.dataset_type,
            "task_spec": {
                "task_type": self._config.task_type,
                "label_space": self._config.label_space,
                "metadata_schema": self._config.metadata_schema,
            },
        }
        r = self._client.post("/api/v1/datasets", json=payload)
        if r.status_code not in (200, 201):
            raise RuntimeError(
                f"dataset creation failed: {r.status_code} {r.text}"
            )
        self._dataset_id = str(r.json()["id"])
        return self._dataset_id

    # -----------------------------------------------------------------------
    # Sample upload
    # -----------------------------------------------------------------------

    def upload_samples(
        self,
        total: int,
        item_builder: Callable[[int], dict[str, Any]],
        *,
        batch_size: int = 5000,
        skip_existing: bool = True,
    ) -> int:
        """Upload *total* samples using *item_builder*.

        Uses the bulk import endpoint for efficiency.  Returns the number
        of samples created.
        """
        if not self._dataset_id:
            raise RuntimeError(
                "dataset_id is not set — ensure_dataset() must be called first"
            )

        if skip_existing:
            existing = self._existing_sample_count()
            if existing > 0:
                self._sample_count = existing
                return existing

        created = 0
        num_batches = math.ceil(total / batch_size)
        t0 = time.time()

        for batch_idx in range(num_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, total)
            items = [item_builder(idx) for idx in range(start, end)]

            r = self._client.post(
                f"/api/v1/datasets/{self._dataset_id}/samples/import",
                json={"items": items},
            )
            if r.status_code not in (200, 201):
                raise RuntimeError(
                    f"sample import failed (batch {batch_idx + 1}): "
                    f"{r.status_code} {r.text[:200]}"
                )
            imported = r.json().get("imported", len(items))
            created += imported

            elapsed = time.time() - t0
            rate = created / elapsed if elapsed > 0 else 0
            pct = 100 * (batch_idx + 1) / num_batches
            print(
                f"    [{batch_idx + 1}/{num_batches}] {created}/{total} "
                f"samples ({pct:.0f}%) — {rate:.1f} samples/s"
            )

        self._sample_count = created
        elapsed = time.time() - t0
        if elapsed > 0:
            print(
                f"\n  Uploaded {created} samples in {elapsed:.1f}s "
                f"({created / elapsed:.1f} samples/s)"
            )
        return created

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _existing_sample_count(self) -> int:
        r = self._client.get(
            f"/api/v1/datasets/{self._dataset_id}/samples",
            params={"offset": 0, "limit": 1},
        )
        if r.status_code != 200:
            return 0
        return int(r.json().get("total", 0))
