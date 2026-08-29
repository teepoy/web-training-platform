from __future__ import annotations

import pytest

from sc_upstream_simulator.settings import SimulatorSettings


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
