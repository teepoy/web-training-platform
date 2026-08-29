from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from omegaconf import DictConfig, OmegaConf
from pydantic import BaseModel, ConfigDict, Field


_SUPPORTED_PROFILES = frozenset({"dev", "pre-release", "prod", "test"})
_PROFILE_ENV = {
    "dev": "dev",
    "pre-release": "pre-release",
    "prod": "prod",
    "test": "test",
}
_INSECURE_SECRET_VALUES = frozenset({"replace-me-in-production"})


class ConfigSection(BaseModel):
    """Typed config section that ignores retired fields on compatibility reads."""

    model_config = ConfigDict(extra="ignore")


class AppSection(ConfigSection):
    env: str = "dev"
    frontend_url: str = ""


class ExecutionConfig(ConfigSection):
    engine: str = "local"
    status_reconcile_interval_seconds: float = 2.0


class LoggingConfig(ConfigSection):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class DatabaseConfig(ConfigSection):
    url: str = ""
    echo: bool = False
    auto_create: bool = False


class MinioLifecycleExportsConfig(ConfigSection):
    enabled: bool = True
    prefix: str = "exports/"
    expiration_days: int = 1


class MinioLifecycleConfig(ConfigSection):
    exports: MinioLifecycleExportsConfig = Field(
        default_factory=MinioLifecycleExportsConfig
    )


class MinioConfig(ConfigSection):
    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    bucket: str = "finetune-artifacts"
    secure: bool = False
    lifecycle: MinioLifecycleConfig = Field(default_factory=MinioLifecycleConfig)


class StorageConfig(ConfigSection):
    kind: str = "minio"
    minio: MinioConfig = Field(default_factory=MinioConfig)
    runtime_bucket: str = "finetune-runtime-inputs"
    sparse_manifest_cache_max_bytes: int = 16_777_216


class K8sConfig(ConfigSection):
    namespace: str = "default"
    incluster: bool = False
    kubeconfig: str | None = None


class KubeflowConfig(ConfigSection):
    group: str = "kubeflow.org"
    version: str = "v1"
    plural: str = "pytorchjobs"
    image: str = "python:3.11-slim"


class WebhookConfig(ConfigSection):
    endpoint: str = "http://localhost:9000/hooks/training"
    timeout_seconds: int = 5


class NotificationConfig(ConfigSection):
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)


class OAuthProviderConfig(ConfigSection):
    display_name: str = ""
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    authorize_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    user_emails_url: str = ""
    scopes: list[str] = Field(default_factory=list)
    user_mapping: dict[str, str] = Field(default_factory=dict)


class OAuthConfig(ConfigSection):
    enabled: bool = False
    state_secret: str = ""
    providers: dict[str, OAuthProviderConfig] = Field(default_factory=dict)


class PrefectConfig(ConfigSection):
    api_url: str = ""
    ui_url: str = ""


class PredictionConfig(ConfigSection):
    compaction_memory_limit: str = "512MiB"
    compaction_temp_limit: str = "4GiB"
    compaction_row_group_rows: int = 100_000


class DatasetTransferConfig(ConfigSection):
    annotation_import_max_bytes: int = Field(default=67_108_864, gt=0)
    annotation_import_max_records: int = Field(default=300_000, gt=0)
    annotation_batch_rows: int = Field(default=1_000, gt=0)
    parquet_import_max_bytes: int = Field(default=536_870_912, gt=0)
    parquet_import_max_rows: int = Field(default=300_000, gt=0)


class LlmConfig(ConfigSection):
    base_url: str = ""
    api_key: str = ""
    model: str = "qwen/qwen-max"
    timeout_seconds: float = 30


class LabelStudioConfig(ConfigSection):
    url: str = ""
    external_url: str = ""
    api_key: str = ""
    database_url: str = ""


class AgentConfig(ConfigSection):
    enabled: bool = True
    metadata_sample_size: int = 100


class RedisConfig(ConfigSection):
    host: str = ""
    port: int = 6379
    db: int = 0
    password: str = ""


class StartupChecksConfig(ConfigSection):
    dependency_timeout_seconds: float = Field(default=5.0, gt=0)


class AuthConfig(ConfigSection):
    enabled: Literal[True] = True
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


class ScDataProviderConfig(ConfigSection):
    implementation: Literal["duckdb"]
    classify_max_rows: int = Field(gt=0)
    max_compressed_request_bytes: int = Field(gt=0)
    max_decompressed_request_bytes: int = Field(gt=0)
    max_rss_mb: int
    cache_dir: str = ""
    cache_namespace: str = ""
    revision_namespace: str
    duckdb_memory_limit: str
    duckdb_threads: int
    duckdb_temp_directory_size: str
    duckdb_allocator_background_threads: bool
    duckdb_preserve_insertion_order: bool
    duckdb_allocator_flush_threshold: str
    duckdb_allocator_bulk_deallocation_flush_threshold: str
    connection_recycle_rss_mb: int
    worker_count: int
    container_memory_limit_mb: int
    python_overhead_mb: int
    service_headroom_mb: int
    object_cache_max_bytes: int
    object_cache_low_watermark_bytes: int
    object_idle_ttl_seconds: int
    cleanup_interval_seconds: int
    stale_write_seconds: int
    lease_ttl_seconds: int
    lease_heartbeat_seconds: int
    build_lock_ttl_seconds: int
    build_lock_heartbeat_seconds: int
    build_wait_timeout_seconds: int
    build_poll_interval_ms: int
    sql_timeout_seconds: int
    max_response_bytes: int
    arrow_batch_rows: int
    stream_queue_capacity: int
    stream_queue_poll_interval_ms: int
    sse_heartbeat_seconds: int
    sse_max_connection_seconds: int


class ScPipelineConfig(ConfigSection):
    import_batch_rows: int
    index_row_group_rows: int
    materialization_batch_rows: int
    materialization_max_error_records: int
    prediction_input_batch_rows: int
    prediction_preprocess_task_rows: int
    prediction_preprocess_workers: int
    prediction_preprocess_prefetch_tasks: int
    prediction_progress_flush_rows: int
    prediction_progress_flush_seconds: float
    prediction_write_batch_rows: int
    training_max_rows: int
    training_max_materialized_bytes: int
    training_shuffle_seed: int


class ScUpstreamConfig(ConfigSection):
    grpc_addr: str = ""
    flight_addr: str = ""


class ScImageParserConfig(ConfigSection):
    grpc_addr: str = ""


class ScConfig(ConfigSection):
    data_provider: ScDataProviderConfig
    pipeline: ScPipelineConfig
    upstream: ScUpstreamConfig = Field(default_factory=ScUpstreamConfig)
    image_parser: ScImageParserConfig = Field(default_factory=ScImageParserConfig)


def _default_sc_config() -> ScConfig:
    base = OmegaConf.load(_config_root() / "base.yaml")
    data = OmegaConf.to_container(base.sc, resolve=True)
    return ScConfig.model_validate(data)


class AppConfig(ConfigSection):
    app: AppSection = Field(default_factory=AppSection)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    k8s: K8sConfig = Field(default_factory=K8sConfig)
    kubeflow: KubeflowConfig = Field(default_factory=KubeflowConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    oauth: OAuthConfig = Field(default_factory=OAuthConfig)
    prefect: PrefectConfig = Field(default_factory=PrefectConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    label_studio: LabelStudioConfig = Field(default_factory=LabelStudioConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    startup_checks: StartupChecksConfig = Field(default_factory=StartupChecksConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    sc: ScConfig = Field(default_factory=_default_sc_config)
    prediction: PredictionConfig = Field(default_factory=PredictionConfig)
    dataset_transfer: DatasetTransferConfig = Field(
        default_factory=DatasetTransferConfig
    )


# Environment-owned values are restricted to secrets and deployment topology.
# Stable application behavior, limits, buckets, models, and tuning live only in
# the selected tracked YAML profile.
_ENVIRONMENT_CONFIG_PATHS = {
    "FRONTEND_URL": "app.frontend_url",
    "DATABASE_URL": "db.url",
    "MINIO_ENDPOINT": "storage.minio.endpoint",
    "MINIO_ACCESS_KEY": "storage.minio.access_key",
    "MINIO_SECRET_KEY": "storage.minio.secret_key",
    "LABEL_STUDIO_URL": "label_studio.url",
    "LABEL_STUDIO_EXTERNAL_URL": "label_studio.external_url",
    "LABEL_STUDIO_API_KEY": "label_studio.api_key",
    "LABEL_STUDIO_DATABASE_URL": "label_studio.database_url",
    "PREFECT_API_URL": "prefect.api_url",
    "PREFECT_UI_URL": "prefect.ui_url",
    "REDIS_HOST": "redis.host",
    "REDIS_PASSWORD": "redis.password",
    "LLM_BASE_URL": "llm.base_url",
    "LLM_API_KEY": "llm.api_key",
    "JWT_SECRET_KEY": "auth.jwt_secret_key",
    "OAUTH_STATE_SECRET": "oauth.state_secret",
    "OAUTH_GOOGLE_CLIENT_ID": "oauth.providers.google.client_id",
    "OAUTH_GOOGLE_CLIENT_SECRET": "oauth.providers.google.client_secret",
    "OAUTH_GITHUB_CLIENT_ID": "oauth.providers.github.client_id",
    "OAUTH_GITHUB_CLIENT_SECRET": "oauth.providers.github.client_secret",
    "OAUTH_CUSTOM_CLIENT_ID": "oauth.providers.custom.client_id",
    "OAUTH_CUSTOM_CLIENT_SECRET": "oauth.providers.custom.client_secret",
    "SC_UPSTREAM_ADDR": "sc.upstream.grpc_addr",
    "SC_UPSTREAM_FLIGHT_ADDR": "sc.upstream.flight_addr",
    "IMAGE_PARSER_GRPC_ADDR": "sc.image_parser.grpc_addr",
    "SC_DATA_PROVIDER_CACHE_DIR": "sc.data_provider.cache_dir",
    "SC_DATA_PROVIDER_CACHE_NAMESPACE": "sc.data_provider.cache_namespace",
}


def _require(value: str, field_name: str) -> None:
    if not value:
        raise RuntimeError(f"Missing required config: {field_name}")


def _as_app_config(cfg: AppConfig | DictConfig) -> AppConfig:
    if isinstance(cfg, AppConfig):
        return cfg
    config_data = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(config_data, dict):
        raise RuntimeError("Application config must be a mapping")
    return AppConfig.model_validate(config_data)


def _validate_runtime_config(cfg: AppConfig | DictConfig, profile: str) -> None:
    runtime_bucket = (
        OmegaConf.select(cfg, "storage.runtime_bucket", default="")
        if isinstance(cfg, DictConfig)
        else cfg.storage.runtime_bucket
    )
    cfg = _as_app_config(cfg)
    env = str(cfg.app.env)
    engine = str(cfg.execution.engine)
    storage_kind = str(cfg.storage.kind)
    db_url = str(cfg.db.url)

    expected_env = _PROFILE_ENV.get(profile)
    if expected_env is None:
        raise RuntimeError(f"Unsupported config profile: {profile}")
    if profile == "test":
        return
    if env != expected_env:
        raise RuntimeError(
            f"Config profile {profile!r} must set app.env={expected_env!r}, got {env!r}"
        )

    if storage_kind == "memory":
        raise RuntimeError("storage.kind=memory is only supported in the test profile")

    if engine == "local":
        raise RuntimeError(
            "execution.engine=local is only supported in the test profile"
        )

    _require(db_url, "db.url")
    if not db_url.startswith("postgresql"):
        raise RuntimeError("deployable environments require PostgreSQL")

    if storage_kind != "minio":
        raise RuntimeError(
            "dev/prod environments require S3-compatible object storage (storage.kind=minio)"
        )

    _require(str(cfg.prefect.api_url), "prefect.api_url")
    _require(str(cfg.prefect.ui_url), "prefect.ui_url")
    _require(str(cfg.app.frontend_url), "app.frontend_url")
    _require(str(cfg.storage.minio.endpoint), "storage.minio.endpoint")
    _require(str(cfg.storage.minio.access_key), "storage.minio.access_key")
    _require(str(cfg.storage.minio.secret_key), "storage.minio.secret_key")
    _require(str(cfg.storage.minio.bucket), "storage.minio.bucket")
    _require(str(runtime_bucket), "storage.runtime_bucket")
    _require(str(cfg.label_studio.url), "label_studio.url")
    _require(str(cfg.label_studio.external_url), "label_studio.external_url")
    _require(str(cfg.label_studio.api_key), "label_studio.api_key")
    _require(str(cfg.label_studio.database_url), "label_studio.database_url")
    _require(str(cfg.auth.jwt_secret_key), "auth.jwt_secret_key")
    _require(str(cfg.redis.host), "redis.host")
    _require(str(cfg.sc.upstream.grpc_addr), "sc.upstream.grpc_addr")
    _require(str(cfg.sc.upstream.flight_addr), "sc.upstream.flight_addr")
    _require(str(cfg.sc.image_parser.grpc_addr), "sc.image_parser.grpc_addr")
    _require(str(cfg.sc.data_provider.cache_dir), "sc.data_provider.cache_dir")
    _require(
        str(cfg.sc.data_provider.cache_namespace),
        "sc.data_provider.cache_namespace",
    )
    if cfg.auth.jwt_secret_key in _INSECURE_SECRET_VALUES:
        raise RuntimeError("auth.jwt_secret_key must not use a placeholder value")
    if cfg.oauth.enabled:
        _require(str(cfg.oauth.state_secret), "oauth.state_secret")
        if cfg.oauth.state_secret in _INSECURE_SECRET_VALUES:
            raise RuntimeError("oauth.state_secret must not use a placeholder value")
        for provider_name, provider in cfg.oauth.providers.items():
            if not provider.enabled:
                continue
            _require(provider.client_id, f"oauth.providers.{provider_name}.client_id")
            _require(
                provider.client_secret,
                f"oauth.providers.{provider_name}.client_secret",
            )


def _config_root() -> Path:
    return Path(__file__).resolve().parents[2] / "config"


@lru_cache(maxsize=4)
def load_config(skip_runtime_validation: bool = False) -> AppConfig:
    base = OmegaConf.load(_config_root() / "base.yaml")
    profile = os.getenv("APP_CONFIG_PROFILE", "dev")
    if profile not in _SUPPORTED_PROFILES:
        supported = ", ".join(sorted(_SUPPORTED_PROFILES))
        raise RuntimeError(
            f"Unsupported APP_CONFIG_PROFILE={profile!r}; expected one of: {supported}"
        )
    profile_path = _config_root() / f"{profile}.yaml"
    cfg = OmegaConf.merge(base, OmegaConf.load(profile_path))
    for environment_name, config_path in _ENVIRONMENT_CONFIG_PATHS.items():
        raw_value = os.getenv(environment_name)
        if raw_value is not None:
            OmegaConf.update(cfg, config_path, raw_value, merge=False)
    assert isinstance(cfg, DictConfig)
    config_data = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(config_data, dict):
        raise RuntimeError("Application config must be a mapping")
    app_config = AppConfig.model_validate(config_data)
    if not skip_runtime_validation:
        _validate_runtime_config(app_config, profile)
    return app_config
