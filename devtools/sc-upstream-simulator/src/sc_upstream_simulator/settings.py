from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class SimulatorSettings:
    database_url: str
    api_token: str

    @classmethod
    def from_environment(cls) -> SimulatorSettings:
        if os.environ.get("SC_SIMULATOR_ALLOW_MUTATIONS") != "1":
            raise RuntimeError(
                "SC_SIMULATOR_ALLOW_MUTATIONS=1 is required to start the simulator"
            )
        database_url = os.environ.get("SC_SIMULATOR_DATABASE_URL")
        if not database_url:
            raise RuntimeError("SC_SIMULATOR_DATABASE_URL is required")
        if not database_url.startswith("postgresql+asyncpg://"):
            raise RuntimeError("SC_SIMULATOR_DATABASE_URL must use postgresql+asyncpg")
        api_token = os.environ.get("SC_SIMULATOR_API_TOKEN")
        if not api_token:
            raise RuntimeError("SC_SIMULATOR_API_TOKEN is required")
        return cls(database_url=database_url, api_token=api_token)
