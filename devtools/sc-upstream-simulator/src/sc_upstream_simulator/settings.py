from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class SimulatorSettings:
    database_url: str
    api_token: str
    grpc_port: int
    flight_port: int

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
        grpc_port = cls._required_port("SC_SIMULATOR_GRPC_PORT")
        flight_port = cls._required_port("SC_SIMULATOR_FLIGHT_PORT")
        return cls(
            database_url=database_url,
            api_token=api_token,
            grpc_port=grpc_port,
            flight_port=flight_port,
        )

    @staticmethod
    def _required_port(name: str) -> int:
        raw = os.environ.get(name)
        if not raw:
            raise RuntimeError(f"{name} is required")
        try:
            port = int(raw)
        except ValueError as exc:
            raise RuntimeError(f"{name} must be an integer") from exc
        if port < 1 or port > 65535:
            raise RuntimeError(f"{name} must be between 1 and 65535")
        return port
