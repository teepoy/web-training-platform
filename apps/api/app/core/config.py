from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from omegaconf import DictConfig, OmegaConf


def _config_root() -> Path:
    return Path(__file__).resolve().parents[2] / "config"


@lru_cache(maxsize=1)
def load_config() -> DictConfig:
    base = OmegaConf.load(_config_root() / "base.yaml")
    profile = os.getenv("APP_CONFIG_PROFILE", "local-smoke")
    profile_path = _config_root() / f"{profile}.yaml"
    if profile_path.exists():
        cfg = OmegaConf.merge(base, OmegaConf.load(profile_path))
    else:
        cfg = base

    db_url = os.getenv("DATABASE_URL")
    if db_url:
        cfg.db.url = db_url
    minio_endpoint = os.getenv("MINIO_ENDPOINT")
    if minio_endpoint:
        cfg.storage.minio.endpoint = minio_endpoint
    minio_access_key = os.getenv("MINIO_ACCESS_KEY")
    if minio_access_key:
        cfg.storage.minio.access_key = minio_access_key
    minio_secret_key = os.getenv("MINIO_SECRET_KEY")
    if minio_secret_key:
        cfg.storage.minio.secret_key = minio_secret_key
    minio_bucket = os.getenv("MINIO_BUCKET")
    if minio_bucket:
        cfg.storage.minio.bucket = minio_bucket
    ls_url = os.getenv("LABEL_STUDIO_URL")
    if ls_url:
        cfg.label_studio.url = ls_url
    ls_api_key = os.getenv("LABEL_STUDIO_API_KEY")
    if ls_api_key:
        cfg.label_studio.api_key = ls_api_key
    ls_db_url = os.getenv("LABEL_STUDIO_DATABASE_URL")
    if ls_db_url:
        cfg.label_studio.database_url = ls_db_url
    prefect_api_url = os.getenv("PREFECT_API_URL")
    if prefect_api_url:
        cfg.prefect.api_url = prefect_api_url
    embedding_target = os.getenv("EMBEDDING_GRPC_TARGET")
    if embedding_target:
        cfg.embedding.grpc_target = embedding_target
    return cfg
