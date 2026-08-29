from __future__ import annotations

from collections.abc import Callable

from app.core.config import AppConfig, load_config
from app.shared.domain.protocols import ArtifactStorage
from app.shared.infrastructure.storage.minio import (
    MinioArtifactStorage,
    build_minio_export_lifecycle,
)


ArtifactStorageFactory = Callable[[AppConfig], ArtifactStorage]
_EXTERNAL_FACTORIES: dict[str, ArtifactStorageFactory] = {}


def register_artifact_storage_factory(
    kind: str, factory: ArtifactStorageFactory
) -> None:
    """Register an adapter from an explicit non-production composition root."""
    if not kind or kind == "minio":
        raise ValueError("external storage kind must be non-empty and not 'minio'")
    _EXTERNAL_FACTORIES[kind] = factory


def build_artifact_storage(cfg: AppConfig | None = None) -> ArtifactStorage:
    """Build an artifact storage backend from the current config profile.

    Production owns the MinIO adapter. Test-only adapters must be registered by
    the test composition root before application construction.
    """
    cfg = cfg or load_config()
    kind = str(cfg.storage.kind)
    if kind == "minio":
        return MinioArtifactStorage(
            endpoint=str(cfg.storage.minio.endpoint),
            access_key=str(cfg.storage.minio.access_key),
            secret_key=str(cfg.storage.minio.secret_key),
            bucket=str(cfg.storage.minio.bucket),
            secure=bool(cfg.storage.minio.secure),
            export_lifecycle=build_minio_export_lifecycle(cfg),
        )
    factory = _EXTERNAL_FACTORIES.get(kind)
    if factory is None:
        raise RuntimeError(f"No artifact storage adapter registered for kind: {kind}")
    return factory(cfg)
