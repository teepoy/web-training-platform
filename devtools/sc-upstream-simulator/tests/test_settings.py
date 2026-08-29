from __future__ import annotations

import pytest

from sc_upstream_simulator.settings import SimulatorSettings


def _set_complete_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SC_SIMULATOR_ALLOW_MUTATIONS", "1")
    monkeypatch.setenv(
        "SC_SIMULATOR_DATABASE_URL",
        "postgresql+asyncpg://simulator:secret@postgres/sc_simulator",
    )
    monkeypatch.setenv("SC_SIMULATOR_API_TOKEN", "secret")
    monkeypatch.setenv("SC_SIMULATOR_GRPC_PORT", "9091")
    monkeypatch.setenv("SC_SIMULATOR_FLIGHT_PORT", "9093")
    monkeypatch.setenv("SC_SIMULATOR_S3_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("SC_SIMULATOR_S3_ACCESS_KEY", "access")
    monkeypatch.setenv("SC_SIMULATOR_S3_SECRET_KEY", "secret")
    monkeypatch.setenv("SC_SIMULATOR_S3_REGION", "us-east-1")
    monkeypatch.setenv("SC_SIMULATOR_PATCH_BUCKET", "patches")
    monkeypatch.setenv("SC_SIMULATOR_REVIEW_BUCKET", "reviews")


def test_runtime_settings_require_explicit_mutation_enable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SC_SIMULATOR_ALLOW_MUTATIONS", raising=False)
    monkeypatch.setenv(
        "SC_SIMULATOR_DATABASE_URL",
        "postgresql+asyncpg://simulator:secret@postgres/sc_simulator",
    )
    monkeypatch.setenv("SC_SIMULATOR_API_TOKEN", "secret")

    with pytest.raises(RuntimeError, match="SC_SIMULATOR_ALLOW_MUTATIONS=1"):
        SimulatorSettings.from_environment()


def test_runtime_settings_reject_non_postgresql_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SC_SIMULATOR_ALLOW_MUTATIONS", "1")
    monkeypatch.setenv("SC_SIMULATOR_DATABASE_URL", "sqlite+aiosqlite:///sim.db")
    monkeypatch.setenv("SC_SIMULATOR_API_TOKEN", "secret")

    with pytest.raises(RuntimeError, match=r"must use postgresql\+asyncpg"):
        SimulatorSettings.from_environment()


def test_runtime_settings_require_explicit_transport_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SC_SIMULATOR_ALLOW_MUTATIONS", "1")
    monkeypatch.setenv(
        "SC_SIMULATOR_DATABASE_URL",
        "postgresql+asyncpg://simulator:secret@postgres/sc_simulator",
    )
    monkeypatch.setenv("SC_SIMULATOR_API_TOKEN", "secret")
    monkeypatch.delenv("SC_SIMULATOR_GRPC_PORT", raising=False)
    monkeypatch.setenv("SC_SIMULATOR_FLIGHT_PORT", "9093")

    with pytest.raises(RuntimeError, match="SC_SIMULATOR_GRPC_PORT is required"):
        SimulatorSettings.from_environment()


def test_runtime_settings_load_complete_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_complete_environment(monkeypatch)

    settings = SimulatorSettings.from_environment()

    assert settings.grpc_port == 9091
    assert settings.flight_port == 9093
    assert settings.patch_bucket == "patches"


def test_runtime_settings_require_object_store_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_complete_environment(monkeypatch)
    monkeypatch.delenv("SC_SIMULATOR_S3_ENDPOINT")

    with pytest.raises(RuntimeError, match="SC_SIMULATOR_S3_ENDPOINT is required"):
        SimulatorSettings.from_environment()
