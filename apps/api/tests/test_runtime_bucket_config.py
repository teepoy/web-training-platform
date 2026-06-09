"""RED tests for runtime bucket configuration contract.

These tests assert the expected contract for a fixed runtime bucket config key
(``storage.runtime_bucket``) that **all jobs share** — jobs use object-name
prefixes like ``train/{job_id}/`` and ``predict/{job_id}/``, not per-job
buckets.

Assertions
----------
1. The config key ``storage.runtime_bucket`` exists and defaults to
   ``finetune-runtime-inputs`` (never empty).
2. Missing ``runtime_bucket`` config raises a clear ``RuntimeError`` that
   mentions "runtime bucket" (not a generic ``KeyError`` / ``AttributeError``).
3. The runtime bucket is distinct from the existing artifact bucket
   (``finetune-artifacts``).

Status
------
**RED** — the ``storage.runtime_bucket`` key does not exist in
``config/base.yaml`` and no validation check is wired yet.
"""

from __future__ import annotations

import pytest
from omegaconf import DictConfig, OmegaConf


class TestRuntimeBucketKeyExists:
    """The ``storage.runtime_bucket`` config key must exist with a default value."""

    def test_runtime_bucket_has_nonempty_default(self) -> None:
        """``storage.runtime_bucket`` must exist and default to ``finetune-runtime-inputs``."""
        from app.core.config import load_config

        cfg = load_config(skip_runtime_validation=True)
        # RED: ``storage.runtime_bucket`` is not in ``config/base.yaml`` yet.
        # Attribute-style access on a missing OmegaConf key raises
        # ``ConfigAttributeError`` (subclass of ``AttributeError``).
        bucket = cfg.storage.runtime_bucket
        assert bucket, "runtime_bucket must not be empty"
        assert bucket == "finetune-runtime-inputs", (
            f"Expected 'finetune-runtime-inputs', got {bucket!r}"
        )

    def test_runtime_bucket_is_distinct_from_artifact_bucket(self) -> None:
        """The runtime bucket must differ from the artifact bucket (``finetune-artifacts``)."""
        from app.core.config import load_config

        cfg = load_config(skip_runtime_validation=True)
        # RED: same missing-key failure as above.
        runtime = cfg.storage.runtime_bucket
        artifact = cfg.storage.minio.bucket
        assert runtime != artifact, (
            f"Runtime bucket ({runtime!r}) must differ from artifact bucket ({artifact!r})"
        )
        assert runtime == "finetune-runtime-inputs"


class TestRuntimeBucketValidation:
    """When ``storage.runtime_bucket`` is missing, validation must raise a clear error."""

    @staticmethod
    def _config_without_runtime_bucket() -> DictConfig:
        """Build a dev-profile config that satisfies all existing ``_validate_runtime_config``
        checks except the missing ``storage.runtime_bucket``."""
        return OmegaConf.create({
            "app": {"env": "dev"},
            "execution": {"engine": "prefect"},
            "db": {"url": "postgresql+asyncpg://localhost/test"},
            "storage": {
                "kind": "minio",
                "minio": {
                    "endpoint": "localhost:9000",
                    "access_key": "test",
                    "secret_key": "test",
                    "bucket": "finetune-artifacts",
                    "secure": False,
                },
            },
            "prefect": {"api_url": "http://localhost:4200/api"},
            "label_studio": {
                "url": "http://localhost:8080",
                "api_key": "test",
                "database_url": "postgresql://localhost/ls",
            },
        })

    def test_missing_runtime_bucket_raises_runtime_error(self) -> None:
        """``_validate_runtime_config`` must raise ``RuntimeError`` mentioning
        "runtime bucket" when the key is absent."""
        from app.core.config import _validate_runtime_config

        cfg = self._config_without_runtime_bucket()
        # RED: ``storage.runtime_bucket`` validation is not wired yet →
        # ``_validate_runtime_config`` returns without error →
        # ``pytest.raises(RuntimeError, ...)`` fails because no exception
        # was raised.
        with pytest.raises(RuntimeError, match=r"runtime.*bucket"):
            _validate_runtime_config(cfg, profile="dev")

    def test_missing_runtime_bucket_skipped_in_test_profile(self) -> None:
        """The ``test`` profile must skip the runtime bucket check (existing pattern)."""
        from app.core.config import _validate_runtime_config

        cfg = self._config_without_runtime_bucket()
        # Should not raise — test profile skips all validation.
        _validate_runtime_config(cfg, profile="test")
