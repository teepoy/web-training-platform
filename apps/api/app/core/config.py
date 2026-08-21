from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Any, Literal, TypeVar

from omegaconf import DictConfig, OmegaConf
from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")
_SUPPORTED_PROFILES = frozenset({"dev", "pre-release", "prod", "test"})
_PROFILE_ENV = {
    "dev": "dev",
    "pre-release": "pre-release",
    "prod": "prod",
    "test": "test",
}
_INSECURE_SECRET_VALUES = frozenset({"replace-me-in-production"})


class ConfigSection(BaseModel):
    """Typed config section with temporary dict-like access for legacy callers."""

    model_config = ConfigDict(extra="allow")

    def get(self, key: str, default: T | None = None) -> Any | T | None:
        if hasattr(self, key):
            return getattr(self, key)
        extra = self.__pydantic_extra__ or {}
        return extra.get(key, default)


class AppSection(ConfigSection):
    name: str = "online-finetune-api"
    env: str = "dev"
    frontend_url: str = "http://localhost:5173"


class ExecutionConfig(ConfigSection):
    engine: str = "local"
    status_reconcile_interval_seconds: float = 2.0


class DatabaseConfig(ConfigSection):
    url: str = "sqlite+aiosqlite:///./finetune.db"
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
    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
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
    sink: str = "webhook"
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
    state_secret: str = "replace-me-in-production"
    providers: dict[str, OAuthProviderConfig] = Field(default_factory=dict)


class PrefectConfig(ConfigSection):
    api_url: str = "http://localhost:4200/api"
    ui_url: str = "http://localhost:4200"
    work_pool_name: str = "default-cpu"
    work_pool_type: str = "process"
    flow_name: str = "train-job"
    concurrency_limit: int = 1


class PredictionConfig(ConfigSection):
    compaction_memory_limit: str = "512MiB"
    compaction_temp_limit: str = "4GiB"
    compaction_row_group_rows: int = 100_000


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


class DataConfig(ConfigSection):
    dir: str = ""


class SensorsConfig(ConfigSection):
    dir: str = "sensors"
    strict: bool = False


class AgentConfig(ConfigSection):
    enabled: bool = True
    max_panels: int = 8
    metadata_sample_size: int = 100


class RedisConfig(ConfigSection):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = ""


class StartupChecksConfig(ConfigSection):
    dependency_timeout_seconds: float = Field(default=5.0, gt=0)


class AuthConfig(ConfigSection):
    enabled: Literal[True] = True
    jwt_secret_key: str = "replace-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


class ScMockConfig(ConfigSection):
    db_url: str = ""


class ScDataProviderConfig(ConfigSection):
    implementation: Literal["duckdb"]
    max_rss_mb: int
    cache_dir: str
    cache_namespace: str
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
    training_shuffle_buffer_rows: int


class ScConfig(ConfigSection):
    mock: ScMockConfig = Field(default_factory=ScMockConfig)
    data_provider: ScDataProviderConfig
    pipeline: ScPipelineConfig


def _default_sc_config() -> ScConfig:
    base = OmegaConf.load(_config_root() / "base.yaml")
    data = OmegaConf.to_container(base.sc, resolve=True)
    return ScConfig.model_validate(data)


class AppConfig(ConfigSection):
    app: AppSection = Field(default_factory=AppSection)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    k8s: K8sConfig = Field(default_factory=K8sConfig)
    kubeflow: KubeflowConfig = Field(default_factory=KubeflowConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    oauth: OAuthConfig = Field(default_factory=OAuthConfig)
    prefect: PrefectConfig = Field(default_factory=PrefectConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    label_studio: LabelStudioConfig = Field(default_factory=LabelStudioConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    sensors: SensorsConfig = Field(default_factory=SensorsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    startup_checks: StartupChecksConfig = Field(default_factory=StartupChecksConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    sc: ScConfig = Field(default_factory=_default_sc_config)
    prediction: PredictionConfig = Field(default_factory=PredictionConfig)
    model: str = "openai/clip-vit-base-patch32"
    dimension: int = 512


def _require(value: str, field_name: str) -> None:
    if not value:
        raise RuntimeError(f"Missing required config: {field_name}")


def _parse_boolean_environment(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"expected true or false, got {value!r}")


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
    if cfg.auth.jwt_secret_key in _INSECURE_SECRET_VALUES:
        raise RuntimeError("auth.jwt_secret_key must not use a placeholder value")
    if cfg.oauth.enabled:
        _require(str(cfg.oauth.state_secret), "oauth.state_secret")
        if cfg.oauth.state_secret in _INSECURE_SECRET_VALUES:
            raise RuntimeError("oauth.state_secret must not use a placeholder value")


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

    frontend_url = os.getenv("FRONTEND_URL")
    if frontend_url:
        cfg.app.frontend_url = frontend_url
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
    prefect_ui_url = os.getenv("PREFECT_UI_URL")
    if prefect_ui_url:
        cfg.prefect.ui_url = prefect_ui_url
    redis_host = os.getenv("REDIS_HOST")
    if redis_host:
        cfg.redis.host = redis_host
    redis_port = os.getenv("REDIS_PORT")
    if redis_port:
        cfg.redis.port = int(redis_port)
    redis_db = os.getenv("REDIS_DB")
    if redis_db:
        cfg.redis.db = int(redis_db)
    redis_password = os.getenv("REDIS_PASSWORD")
    if redis_password:
        cfg.redis.password = redis_password
    startup_timeout = os.getenv("STARTUP_CHECK_DEPENDENCY_TIMEOUT_SECONDS")
    if startup_timeout:
        cfg.startup_checks.dependency_timeout_seconds = float(startup_timeout)
    data_provider_environment = {
        "SC_DATA_PROVIDER_IMPLEMENTATION": ("implementation", str),
        "SC_DATA_PROVIDER_MAX_RSS_MB": ("max_rss_mb", int),
        "SC_DATA_PROVIDER_CACHE_DIR": ("cache_dir", str),
        "SC_DATA_PROVIDER_CACHE_NAMESPACE": ("cache_namespace", str),
        "SC_DATA_PROVIDER_REVISION_NAMESPACE": ("revision_namespace", str),
        "SC_DATA_PROVIDER_DUCKDB_MEMORY_LIMIT": ("duckdb_memory_limit", str),
        "SC_DATA_PROVIDER_DUCKDB_THREADS": ("duckdb_threads", int),
        "SC_DATA_PROVIDER_DUCKDB_TEMP_DIRECTORY_SIZE": (
            "duckdb_temp_directory_size",
            str,
        ),
        "SC_DATA_PROVIDER_DUCKDB_ALLOCATOR_BACKGROUND_THREADS": (
            "duckdb_allocator_background_threads",
            _parse_boolean_environment,
        ),
        "SC_DATA_PROVIDER_DUCKDB_PRESERVE_INSERTION_ORDER": (
            "duckdb_preserve_insertion_order",
            _parse_boolean_environment,
        ),
        "SC_DATA_PROVIDER_DUCKDB_ALLOCATOR_FLUSH_THRESHOLD": (
            "duckdb_allocator_flush_threshold",
            str,
        ),
        "SC_DATA_PROVIDER_DUCKDB_ALLOCATOR_BULK_DEALLOCATION_FLUSH_THRESHOLD": (
            "duckdb_allocator_bulk_deallocation_flush_threshold",
            str,
        ),
        "SC_DATA_PROVIDER_CONNECTION_RECYCLE_RSS_MB": (
            "connection_recycle_rss_mb",
            int,
        ),
        "SC_DATA_PROVIDER_WORKER_COUNT": ("worker_count", int),
        "SC_DATA_PROVIDER_CONTAINER_MEMORY_LIMIT_MB": (
            "container_memory_limit_mb",
            int,
        ),
        "SC_DATA_PROVIDER_PYTHON_OVERHEAD_MB": ("python_overhead_mb", int),
        "SC_DATA_PROVIDER_SERVICE_HEADROOM_MB": ("service_headroom_mb", int),
        "SC_DATA_PROVIDER_OBJECT_CACHE_MAX_BYTES": ("object_cache_max_bytes", int),
        "SC_DATA_PROVIDER_OBJECT_CACHE_LOW_WATERMARK_BYTES": (
            "object_cache_low_watermark_bytes",
            int,
        ),
        "SC_DATA_PROVIDER_OBJECT_IDLE_TTL_SECONDS": (
            "object_idle_ttl_seconds",
            int,
        ),
        "SC_DATA_PROVIDER_CLEANUP_INTERVAL_SECONDS": (
            "cleanup_interval_seconds",
            int,
        ),
        "SC_DATA_PROVIDER_STALE_WRITE_SECONDS": ("stale_write_seconds", int),
        "SC_DATA_PROVIDER_LEASE_TTL_SECONDS": ("lease_ttl_seconds", int),
        "SC_DATA_PROVIDER_LEASE_HEARTBEAT_SECONDS": (
            "lease_heartbeat_seconds",
            int,
        ),
        "SC_DATA_PROVIDER_BUILD_LOCK_TTL_SECONDS": (
            "build_lock_ttl_seconds",
            int,
        ),
        "SC_DATA_PROVIDER_BUILD_LOCK_HEARTBEAT_SECONDS": (
            "build_lock_heartbeat_seconds",
            int,
        ),
        "SC_DATA_PROVIDER_BUILD_WAIT_TIMEOUT_SECONDS": (
            "build_wait_timeout_seconds",
            int,
        ),
        "SC_DATA_PROVIDER_BUILD_POLL_INTERVAL_MS": ("build_poll_interval_ms", int),
        "SC_DATA_PROVIDER_SQL_TIMEOUT_SECONDS": ("sql_timeout_seconds", int),
        "SC_DATA_PROVIDER_MAX_RESPONSE_BYTES": ("max_response_bytes", int),
        "SC_DATA_PROVIDER_ARROW_BATCH_ROWS": ("arrow_batch_rows", int),
        "SC_DATA_PROVIDER_STREAM_QUEUE_CAPACITY": ("stream_queue_capacity", int),
        "SC_DATA_PROVIDER_STREAM_QUEUE_POLL_INTERVAL_MS": (
            "stream_queue_poll_interval_ms",
            int,
        ),
        "SC_DATA_PROVIDER_SSE_HEARTBEAT_SECONDS": ("sse_heartbeat_seconds", int),
        "SC_DATA_PROVIDER_SSE_MAX_CONNECTION_SECONDS": (
            "sse_max_connection_seconds",
            int,
        ),
    }
    for environment_name, (field_name, converter) in data_provider_environment.items():
        raw_value = os.getenv(environment_name)
        if raw_value is not None:
            cfg.sc.data_provider[field_name] = converter(raw_value)
    sc_pipeline_environment = {
        "SC_PIPELINE_IMPORT_BATCH_ROWS": ("import_batch_rows", int),
        "SC_PIPELINE_INDEX_ROW_GROUP_ROWS": ("index_row_group_rows", int),
        "SC_PIPELINE_MATERIALIZATION_BATCH_ROWS": (
            "materialization_batch_rows",
            int,
        ),
        "SC_PIPELINE_MATERIALIZATION_MAX_ERROR_RECORDS": (
            "materialization_max_error_records",
            int,
        ),
        "SC_PIPELINE_PREDICTION_INPUT_BATCH_ROWS": (
            "prediction_input_batch_rows",
            int,
        ),
        "SC_PIPELINE_PREDICTION_PREPROCESS_TASK_ROWS": (
            "prediction_preprocess_task_rows",
            int,
        ),
        "SC_PIPELINE_PREDICTION_PREPROCESS_WORKERS": (
            "prediction_preprocess_workers",
            int,
        ),
        "SC_PIPELINE_PREDICTION_PREPROCESS_PREFETCH_TASKS": (
            "prediction_preprocess_prefetch_tasks",
            int,
        ),
        "SC_PIPELINE_PREDICTION_PROGRESS_FLUSH_ROWS": (
            "prediction_progress_flush_rows",
            int,
        ),
        "SC_PIPELINE_PREDICTION_PROGRESS_FLUSH_SECONDS": (
            "prediction_progress_flush_seconds",
            float,
        ),
        "SC_PIPELINE_PREDICTION_WRITE_BATCH_ROWS": (
            "prediction_write_batch_rows",
            int,
        ),
        "SC_PIPELINE_TRAINING_MAX_ROWS": ("training_max_rows", int),
        "SC_PIPELINE_TRAINING_MAX_MATERIALIZED_BYTES": (
            "training_max_materialized_bytes",
            int,
        ),
        "SC_PIPELINE_TRAINING_SHUFFLE_SEED": ("training_shuffle_seed", int),
        "SC_PIPELINE_TRAINING_SHUFFLE_BUFFER_ROWS": (
            "training_shuffle_buffer_rows",
            int,
        ),
    }
    for environment_name, (field_name, converter) in sc_pipeline_environment.items():
        raw_value = os.getenv(environment_name)
        if raw_value is not None:
            cfg.sc.pipeline[field_name] = converter(raw_value)
    prediction_environment = {
        "PREDICTION_COMPACTION_MEMORY_LIMIT": ("compaction_memory_limit", str),
        "PREDICTION_COMPACTION_TEMP_LIMIT": ("compaction_temp_limit", str),
        "PREDICTION_COMPACTION_ROW_GROUP_ROWS": ("compaction_row_group_rows", int),
    }
    for environment_name, (field_name, converter) in prediction_environment.items():
        raw_value = os.getenv(environment_name)
        if raw_value is not None:
            cfg.prediction[field_name] = converter(raw_value)
    llm_base_url = os.getenv("LLM_BASE_URL")
    if llm_base_url:
        cfg.llm.base_url = llm_base_url
    llm_api_key = os.getenv("LLM_API_KEY")
    if llm_api_key:
        cfg.llm.api_key = llm_api_key
    llm_model = os.getenv("LLM_MODEL")
    if llm_model:
        cfg.llm.model = llm_model
    jwt_secret_key = os.getenv("JWT_SECRET_KEY")
    if jwt_secret_key:
        cfg.auth.jwt_secret_key = jwt_secret_key
    oauth_state_secret = os.getenv("OAUTH_STATE_SECRET")
    if oauth_state_secret:
        cfg.oauth.state_secret = oauth_state_secret
    mnt = os.getenv("MNT")
    if mnt:
        cfg.data.dir = mnt
    assert isinstance(cfg, DictConfig)
    config_data = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(config_data, dict):
        raise RuntimeError("Application config must be a mapping")
    app_config = AppConfig.model_validate(config_data)
    if not skip_runtime_validation:
        _validate_runtime_config(app_config, profile)
    return app_config
