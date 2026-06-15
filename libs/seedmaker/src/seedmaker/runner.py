from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from seedmaker.auth import (
    register_seed_user,
    login_seed_user,
    promote_superadmin,
    resolve_or_create_org,
)
from seedmaker.utils import (
    _find_by_name,
    api_request,
    wait_for_api_ready,
    DEFAULT_COMPOSE_FILE,
    DEFAULT_SEED_EMAIL,
    DEFAULT_SEED_PASSWORD,
    DEFAULT_SEED_NAME,
    DEFAULT_ORG_NAME,
    DEFAULT_ORG_SLUG,
)

import httpx
import math
import sys
import time


@dataclass
class SeedConfig:
    name: str
    dataset_name: str = ""
    description: str = ""
    label_space: list[str] = field(default_factory=list)
    dataset_type: str = "image_sc"
    task_type: str = "patch"
    metadata_schema: dict = field(default_factory=dict)
    defer_dataset: bool = False
    storage_mode: str = "db_full"
    org_name: str = DEFAULT_ORG_NAME
    org_slug: str = DEFAULT_ORG_SLUG
    compose_file: str = DEFAULT_COMPOSE_FILE
    seed_email: str = DEFAULT_SEED_EMAIL
    seed_password: str = DEFAULT_SEED_PASSWORD
    seed_name: str = DEFAULT_SEED_NAME


class SeedRunner:
    def __init__(
        self,
        config: SeedConfig,
        api_url: str = "http://localhost:8000",
        no_promote: bool = False,
    ) -> None:
        self.config = config
        self.client = httpx.Client(base_url=api_url.rstrip("/"), timeout=60.0)
        self.no_promote = no_promote
        self._dataset_id: str | None = None
        self._sample_count: int = 0

    @property
    def dataset_id(self) -> str | None:
        return self._dataset_id

    def setup(self, skip_dataset: bool = False) -> str | None:
        self._wait()
        self._register_user()
        self._promote()
        self._login()
        self._ensure_org()
        if not skip_dataset:
            self._ensure_dataset()
        return self._dataset_id

    def ensure_dataset(self) -> str | None:
        self._ensure_dataset()
        return self._dataset_id

    def upload_samples(
        self,
        total: int,
        item_builder: Callable[[int], dict],
        *,
        batch_size: int = 5000,
        loader: Callable[[list[dict]], int] | None = None,
        skip_existing: bool = True,
    ) -> int:
        if skip_existing:
            existing = self._existing_sample_count()
            if existing > 0:
                print(f"  Dataset already has {existing} samples, skipping.")
                self._sample_count = existing
                return existing

        if loader is None:
            from seedmaker.loaders.dataset import DatasetLoader

            if self._dataset_id is None:
                raise RuntimeError(
                    "dataset_id is not set — ensure_dataset() must be called first"
                )
            loader = DatasetLoader(self.client, self._dataset_id)

        created = 0
        num_batches = math.ceil(total / batch_size)
        t0 = time.time()

        for batch_idx in range(num_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, total)
            batch = [item_builder(idx) for idx in range(start, end)]

            imported = loader(batch)
            created += imported

            elapsed = time.time() - t0
            rate = created / elapsed if elapsed > 0 else 0
            pct = 100 * (batch_idx + 1) / num_batches
            print(
                f"    [{batch_idx + 1}/{num_batches}] {created}/{total} "
                f"samples ({pct:.0f}%) — {rate:.1f} samples/s"
            )

        elapsed = time.time() - t0
        self._sample_count = created
        getattr(loader, "flush", lambda: None)()
        print(
            f"\n  Uploaded {created} samples in {elapsed:.1f}s "
            f"({created / elapsed:.1f} samples/s)"
        )
        return created

    def summary(self) -> None:
        print(f"\n{'=' * 50}")
        print("  Seed Summary")
        print(f"{'=' * 50}")
        print(f"  Dataset:    {self.config.dataset_name}")
        print(f"  Dataset ID: {self._dataset_id}")
        print(f"  Labels:     {len(self.config.label_space)} classes")
        print(f"  Samples:    {self._sample_count}")
        print(f"{'=' * 50}")

    def _wait(self) -> None:
        print("[0/6] Waiting for API readiness ...")
        try:
            wait_for_api_ready(self.client)
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)

    def _register_user(self) -> None:
        print("[1/6] Registering seed user ...")
        r = register_seed_user(
            self.client,
            self.config.seed_email,
            self.config.seed_password,
            self.config.seed_name,
        )
        if r.status_code == 201:
            print(f"  Created user: {self.config.seed_email}")
        elif r.status_code == 409:
            print("  User already exists, skipping.")
        else:
            print(f"  Warning: register returned {r.status_code}: {r.text}")

    def _promote(self) -> None:
        print("[2/6] Promoting to superadmin ...")
        if self.no_promote:
            print("  Skipped (--no-promote).")
        else:
            promote_superadmin(
                self.config.compose_file,
                self.config.seed_email,
                self.config.seed_password,
                self.config.seed_name,
            )

    def _login(self) -> None:
        print("[3/6] Logging in ...")
        r = login_seed_user(
            self.client, self.config.seed_email, self.config.seed_password
        )
        if r.status_code != 200:
            print(f"  ERROR: login failed: {r.status_code} {r.text}")
            sys.exit(1)
        self.client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        print("  Logged in.")

    def _ensure_org(self) -> None:
        print("[4/6] Resolving organization ...")
        org_id = resolve_or_create_org(
            self.client, self.config.org_name, self.config.org_slug
        )
        if org_id:
            print(f"  Using org: {org_id}")
            self.client.headers["X-Organization-ID"] = org_id
        else:
            print(
                "  Warning: could not resolve organization; continuing without X-Organization-ID"
            )

    def _ensure_dataset(self) -> None:
        print(f"[5/6] Creating/finding dataset '{self.config.dataset_name}' ...")
        r = api_request(self.client, "get", "/api/v1/datasets")
        datasets = r.json() if r.status_code == 200 else []
        dataset = _find_by_name(datasets, self.config.dataset_name)
        if dataset is not None:
            self._dataset_id = str(dataset["id"])
            print(f"  Dataset already exists: {self._dataset_id}")
            return
        r = api_request(
            self.client,
            "post",
            "/api/v1/datasets",
            json={
                "name": self.config.dataset_name,
                "dataset_type": self.config.dataset_type,
                "storage_mode": self.config.storage_mode,
                "task_spec": {
                    "task_type": self.config.task_type,
                    "label_space": self.config.label_space,
                    "metadata_schema": self.config.metadata_schema,
                },
            },
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"dataset creation failed: {r.status_code} {r.text}")
        self._dataset_id = str(r.json()["id"])
        print(f"  Created dataset: {self._dataset_id}")

    def _existing_sample_count(self) -> int:
        r = api_request(
            self.client,
            "get",
            f"/api/v1/datasets/{self._dataset_id}/samples?offset=0&limit=1",
        )
        if r.status_code != 200:
            print(f"  WARN: sample count check failed: {r.status_code} {r.text[:120]}")
            return 0
        return int(r.json().get("total", 0))
