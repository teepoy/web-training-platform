from __future__ import annotations

from typing import Any

from app.shared.domain.protocols import ArtifactStorage
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage
from app.shared.infrastructure.storage.minio import MinioArtifactStorage

_INSTANCE: ArtifactStorage | None = None


def init_storage(cfg: Any) -> None:
    global _INSTANCE

    kind = str(cfg.storage.kind)
    if kind == "memory":
        _INSTANCE = InMemoryArtifactStorage()
        return
    if kind == "minio":
        _INSTANCE = MinioArtifactStorage(
            endpoint=str(cfg.storage.minio.endpoint),
            access_key=str(cfg.storage.minio.access_key),
            secret_key=str(cfg.storage.minio.secret_key),
            bucket=str(cfg.storage.minio.bucket),
            secure=bool(cfg.storage.minio.secure),
        )
        return
    raise RuntimeError(f"Unsupported storage.kind: {kind}")


def get_storage() -> ArtifactStorage:
    if _INSTANCE is None:
        raise RuntimeError("Storage infrastructure has not been initialized")
    return _INSTANCE
