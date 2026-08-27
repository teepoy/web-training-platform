from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.config import AuthConfig, load_config


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


def test_pre_release_profile_accepts_explicit_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "APP_CONFIG_PROFILE": "pre-release",
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
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    cfg = load_config()

    assert cfg.app.env == "pre-release"
    assert cfg.auth.jwt_secret_key == "test-environment-jwt-secret"


def test_sc_runtime_and_prediction_storage_accept_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_CONFIG_PROFILE", "test")
    monkeypatch.setenv("SC_PIPELINE_IMPORT_BATCH_ROWS", "4096")
    monkeypatch.setenv("SC_PIPELINE_TRAINING_MAX_ROWS", "12345")
    monkeypatch.setenv("SC_PIPELINE_TRAINING_SHUFFLE_SEED", "91")
    monkeypatch.setenv("SC_PIPELINE_PREDICTION_PROGRESS_FLUSH_ROWS", "777")
    monkeypatch.setenv("SC_PIPELINE_PREDICTION_PROGRESS_FLUSH_SECONDS", "2.5")
    monkeypatch.setenv("PREDICTION_COMPACTION_MEMORY_LIMIT", "256MiB")

    cfg = load_config(skip_runtime_validation=True)

    assert cfg.sc.pipeline.import_batch_rows == 4096
    assert cfg.sc.pipeline.training_max_rows == 12345
    assert cfg.sc.pipeline.training_shuffle_seed == 91
    assert cfg.sc.pipeline.prediction_progress_flush_rows == 777
    assert cfg.sc.pipeline.prediction_progress_flush_seconds == 2.5
    assert cfg.prediction.compaction_memory_limit == "256MiB"


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
    for name in (
        "SC_DATA_PROVIDER_CACHE_DIR",
        "SC_DATA_PROVIDER_WORKER_COUNT",
        "SC_DATA_PROVIDER_CONTAINER_MEMORY_LIMIT_MB",
        "SC_DATA_PROVIDER_SERVICE_HEADROOM_MB",
    ):
        monkeypatch.delenv(name, raising=False)

    cfg = load_config(skip_runtime_validation=True)

    assert cfg.sc.data_provider.cache_dir == expected_cache_dir
    assert cfg.sc.data_provider.worker_count == expected_worker_count
    assert (
        cfg.sc.data_provider.container_memory_limit_mb
        == expected_container_memory_mb
    )
    assert cfg.sc.data_provider.service_headroom_mb == expected_service_headroom_mb
