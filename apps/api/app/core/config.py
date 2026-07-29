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


class DatabaseConfig(ConfigSection):
    url: str = "sqlite+aiosqlite:///./finetune.db"
    echo: bool = False
    auto_create: bool = False


class MinioLifecycleExportsConfig(ConfigSection):
    enabled: bool = True
    prefix: str = "exports/"
    expiration_days: int = 1
    abort_incomplete_multipart_upload_days: int | None = 1


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


class RuntimeDeploymentConfig(ConfigSection):
    deployment: str
    input_contract: str
    output_contract: str
    resource_profile: Literal["cpu", "gpu"]
    owner: Literal["local_compat", "external"]
    algo_id: str
    algo_version: str
    missing_image_policy: Literal["fail", "skip"] | None = None


class RuntimeRoutingConfig(ConfigSection):
    training_routes: dict[str, RuntimeDeploymentConfig] = Field(default_factory=dict)
    train_and_predict_routes: dict[str, RuntimeDeploymentConfig] = Field(
        default_factory=dict
    )
    prediction_routes: dict[str, RuntimeDeploymentConfig] = Field(default_factory=dict)
    materialization_routes: dict[str, RuntimeDeploymentConfig] = Field(
        default_factory=dict
    )


class PredictionConfig(ConfigSection):
    sparse_chunk_size: int = 32


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


class AuthConfig(ConfigSection):
    enabled: bool = True
    jwt_secret_key: str = "replace-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


class ScMockConfig(ConfigSection):
    db_url: str = ""


class ScConfig(ConfigSection):
    mock: ScMockConfig = Field(default_factory=ScMockConfig)


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
    runtime_routing: RuntimeRoutingConfig = Field(default_factory=RuntimeRoutingConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    label_studio: LabelStudioConfig = Field(default_factory=LabelStudioConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    sensors: SensorsConfig = Field(default_factory=SensorsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    sc: ScConfig = Field(default_factory=ScConfig)
    prediction: PredictionConfig = Field(default_factory=PredictionConfig)
    model: str = "openai/clip-vit-base-patch32"
    dimension: int = 512


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
    if cfg.auth.enabled:
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
