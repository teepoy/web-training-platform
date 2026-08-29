from __future__ import annotations

from collections.abc import Iterator

import pytest
from omegaconf import OmegaConf

from app.core.config import (
    _ENVIRONMENT_CONFIG_PATHS,
    _config_root,
    AuthConfig,
    load_config,
)


@pytest.fixture(autouse=True)
def clear_config_cache() -> Iterator[None]:
    load_config.cache_clear()
    yield
    load_config.cache_clear()


def test_unknown_profile_fails_instead_of_loading_base_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_CONFIG_PROFILE", "staging")

    with pytest.raises(RuntimeError, match="Unsupported APP_CONFIG_PROFILE"):
        load_config()


@pytest.mark.parametrize(
    ("profile", "expected_env"),
    [
        ("dev", "dev"),
        ("pre-release", "pre-release"),
        ("prod", "prod"),
        ("test", "test"),
    ],
)
def test_supported_profile_sets_matching_environment(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    expected_env: str,
) -> None:
    monkeypatch.setenv("APP_CONFIG_PROFILE", profile)

    cfg = load_config(skip_runtime_validation=True)

    assert cfg.app.env == expected_env
    assert cfg.auth.enabled is True


def test_auth_configuration_cannot_be_disabled() -> None:
    with pytest.raises(ValueError, match="enabled"):
        AuthConfig.model_validate({"enabled": False})


@pytest.mark.parametrize("profile", ["pre-release", "prod"])
def test_deployable_profiles_require_runtime_secrets(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
) -> None:
    monkeypatch.setenv("APP_CONFIG_PROFILE", profile)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="Missing required config"):
        load_config()


@pytest.mark.parametrize("profile", ["pre-release", "prod"])
def test_deployable_profile_accepts_explicit_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
) -> None:
    values = {
        "APP_CONFIG_PROFILE": profile,
        "FRONTEND_URL": "https://test.example.com",
        "DATABASE_URL": "postgresql+asyncpg://user:password@postgres:5432/finetune",
        "PREFECT_API_URL": "http://prefect-server:4200/api",
        "PREFECT_UI_URL": "https://prefect.test.example.com",
        "LABEL_STUDIO_URL": "http://label-studio:8080",
        "LABEL_STUDIO_EXTERNAL_URL": "https://labels.test.example.com",
        "LABEL_STUDIO_API_KEY": "test-environment-token",
        "LABEL_STUDIO_DATABASE_URL": (
            "postgresql+asyncpg://user:password@postgres:5432/labelstudio"
        ),
        "MINIO_ENDPOINT": "minio:9000",
        "MINIO_ACCESS_KEY": "test-access-key",
        "MINIO_SECRET_KEY": "test-secret-key",
        "JWT_SECRET_KEY": "test-environment-jwt-secret",
        "REDIS_HOST": "redis",
        "SC_UPSTREAM_ADDR": "sc-upstream:9091",
        "SC_UPSTREAM_FLIGHT_ADDR": "grpc://sc-upstream:9093",
        "IMAGE_PARSER_GRPC_ADDR": "image-parser:9092",
        "SC_DATA_PROVIDER_CACHE_DIR": "/mnt/sc-data-provider-cache",
        "SC_DATA_PROVIDER_CACHE_NAMESPACE": "sc-data-provider",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    cfg = load_config()

    assert cfg.app.env == profile
    assert cfg.auth.jwt_secret_key == "test-environment-jwt-secret"


def test_profile_owned_settings_ignore_retired_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_CONFIG_PROFILE", "test")
    monkeypatch.setenv("MINIO_BUCKET", "retired-bucket")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("STARTUP_CHECK_DEPENDENCY_TIMEOUT_SECONDS", "99")
    monkeypatch.setenv("LLM_MODEL", "retired-model")
    monkeypatch.setenv("SC_PIPELINE_IMPORT_BATCH_ROWS", "4096")
    monkeypatch.setenv("PREDICTION_COMPACTION_MEMORY_LIMIT", "256MiB")

    cfg = load_config(skip_runtime_validation=True)

    assert cfg.storage.minio.bucket == "finetune-artifacts"
    assert cfg.redis.port == 6379
    assert cfg.startup_checks.dependency_timeout_seconds == 5
    assert cfg.llm.model == "qwen/qwen-max"
    assert cfg.sc.pipeline.import_batch_rows == 25_000
    assert cfg.prediction.compaction_memory_limit == "512MiB"


def test_deployment_owned_sc_endpoints_use_central_config_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_CONFIG_PROFILE", "test")
    monkeypatch.setenv("SC_UPSTREAM_ADDR", "upstream.example:19091")
    monkeypatch.setenv(
        "SC_UPSTREAM_FLIGHT_ADDR", "grpc://upstream.example:19093"
    )
    monkeypatch.setenv("IMAGE_PARSER_GRPC_ADDR", "parser.example:19092")
    monkeypatch.setenv("SC_DATA_PROVIDER_CACHE_DIR", "/cache/sc")
    monkeypatch.setenv("SC_DATA_PROVIDER_CACHE_NAMESPACE", "sc-pod-1")

    cfg = load_config(skip_runtime_validation=True)

    assert cfg.sc.upstream.grpc_addr == "upstream.example:19091"
    assert cfg.sc.upstream.flight_addr == "grpc://upstream.example:19093"
    assert cfg.sc.image_parser.grpc_addr == "parser.example:19092"
    assert cfg.sc.data_provider.cache_dir == "/cache/sc"
    assert cfg.sc.data_provider.cache_namespace == "sc-pod-1"


def test_prod_yaml_does_not_define_environment_owned_settings() -> None:
    prod = OmegaConf.load(_config_root() / "prod.yaml")

    duplicated_paths = [
        path
        for path in _ENVIRONMENT_CONFIG_PATHS.values()
        if OmegaConf.select(prod, path, default=None) is not None
    ]

    assert duplicated_paths == []


@pytest.mark.parametrize(
    (
        "profile",
        "expected_cache_dir",
        "expected_worker_count",
        "expected_container_memory_mb",
        "expected_service_headroom_mb",
    ),
    [
        ("dev", "/var/cache/sc-data-provider", 1, 6144, 512),
        ("pre-release", "/mnt/sc-data-provider-cache", 4, 6144, 512),
        ("prod", "/mnt/sc-data-provider-cache", 4, 6144, 512),
    ],
)
def test_deployable_sc_data_provider_values_come_from_profiles(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    expected_cache_dir: str,
    expected_worker_count: int,
    expected_container_memory_mb: int,
    expected_service_headroom_mb: int,
) -> None:
    monkeypatch.setenv("APP_CONFIG_PROFILE", profile)
    monkeypatch.setenv("SC_DATA_PROVIDER_CACHE_DIR", expected_cache_dir)
    monkeypatch.setenv("SC_DATA_PROVIDER_CACHE_NAMESPACE", "sc-data-provider")
    monkeypatch.setenv("SC_DATA_PROVIDER_WORKER_COUNT", "999")
    monkeypatch.setenv("SC_DATA_PROVIDER_CONTAINER_MEMORY_LIMIT_MB", "999")
    monkeypatch.setenv("SC_DATA_PROVIDER_SERVICE_HEADROOM_MB", "999")

    cfg = load_config(skip_runtime_validation=True)

    assert cfg.sc.data_provider.cache_dir == expected_cache_dir
    assert cfg.sc.data_provider.worker_count == expected_worker_count
    assert (
        cfg.sc.data_provider.container_memory_limit_mb
        == expected_container_memory_mb
    )
    assert cfg.sc.data_provider.service_headroom_mb == expected_service_headroom_mb
