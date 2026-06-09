from __future__ import annotations

from typing import Any

from app.core.config import load_config
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage
from app.shared.infrastructure.storage.minio import MinioArtifactStorage


def build_artifact_storage() -> Any:
    """Build an artifact storage backend from the current config profile.

    Returns a :class:`MinioArtifactStorage` when ``storage.kind`` is ``minio``,
    otherwise an :class:`InMemoryArtifactStorage`.
    """
    cfg = load_config()
    if str(cfg.storage.kind) == "minio":
        return MinioArtifactStorage(
            endpoint=str(cfg.storage.minio.endpoint),
            access_key=str(cfg.storage.minio.access_key),
            secret_key=str(cfg.storage.minio.secret_key),
            bucket=str(cfg.storage.minio.bucket),
            secure=bool(cfg.storage.minio.secure),
        )
    return InMemoryArtifactStorage()
