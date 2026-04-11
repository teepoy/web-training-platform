from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from omegaconf import DictConfig, OmegaConf


def _require(value: str, field_name: str) -> None:
    if not value:
        raise RuntimeError(f"Missing required config: {field_name}")


def _validate_runtime_config(cfg: DictConfig, profile: str) -> None:
    env = str(cfg.app.env)
    engine = str(cfg.execution.engine)
    storage_kind = str(cfg.storage.kind)
    db_url = str(cfg.db.url)

    if profile == "test" or env == "test":
        return

    if storage_kind == "memory":
        raise RuntimeError("storage.kind=memory is only supported in the test profile")

    if engine == "local":
        raise RuntimeError("execution.engine=local is only supported in the test profile")

    if not db_url.startswith("postgresql"):
        raise RuntimeError("dev/prod environments require PostgreSQL")

    if storage_kind != "minio":
        raise RuntimeError("dev/prod environments require S3-compatible object storage (storage.kind=minio)")

    _require(str(cfg.prefect.api_url), "prefect.api_url")
    _require(str(cfg.storage.minio.endpoint), "storage.minio.endpoint")
    _require(str(cfg.storage.minio.access_key), "storage.minio.access_key")
    _require(str(cfg.storage.minio.secret_key), "storage.minio.secret_key")
    _require(str(cfg.storage.minio.bucket), "storage.minio.bucket")
    _require(str(cfg.label_studio.url), "label_studio.url")
    _require(str(cfg.label_studio.api_key), "label_studio.api_key")
    _require(str(cfg.label_studio.database_url), "label_studio.database_url")
    _require(str(cfg.inference.base_url), "inference.base_url")


def _config_root() -> Path:
    return Path(__file__).resolve().parents[2] / "config"


@lru_cache(maxsize=4)
def load_config(skip_runtime_validation: bool = False) -> DictConfig:
    base = OmegaConf.load(_config_root() / "base.yaml")
    profile = os.getenv("APP_CONFIG_PROFILE", "dev")
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
    ls_external_url = os.getenv("LABEL_STUDIO_EXTERNAL_URL")
    if ls_external_url:
        cfg.label_studio.external_url = ls_external_url
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
    inference_base_url = os.getenv("INFERENCE_BASE_URL")
    if inference_base_url:
        cfg.inference.base_url = inference_base_url
    llm_provider = os.getenv("LLM_PROVIDER")
    if llm_provider:
        cfg.llm.provider = llm_provider
    llm_base_url = os.getenv("LLM_BASE_URL")
    if llm_base_url:
        cfg.llm.base_url = llm_base_url
    llm_api_key = os.getenv("LLM_API_KEY")
    if llm_api_key:
        cfg.llm.api_key = llm_api_key
    llm_model = os.getenv("LLM_MODEL")
    if llm_model:
        cfg.llm.model = llm_model
    if not skip_runtime_validation:
        _validate_runtime_config(cfg, profile)
    return cfg
