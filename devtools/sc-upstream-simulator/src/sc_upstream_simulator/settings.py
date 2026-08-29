from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class SimulatorSettings:
    database_url: str
    api_token: str
    grpc_port: int
    flight_port: int
    object_store_endpoint: str
    object_store_access_key: str
    object_store_secret_key: str
    object_store_region: str
    patch_bucket: str
    review_bucket: str

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
        object_store_endpoint = cls._required("SC_SIMULATOR_S3_ENDPOINT")
        object_store_access_key = cls._required("SC_SIMULATOR_S3_ACCESS_KEY")
        object_store_secret_key = cls._required("SC_SIMULATOR_S3_SECRET_KEY")
        object_store_region = cls._required("SC_SIMULATOR_S3_REGION")
        patch_bucket = cls._required("SC_SIMULATOR_PATCH_BUCKET")
        review_bucket = cls._required("SC_SIMULATOR_REVIEW_BUCKET")
        return cls(
            database_url=database_url,
            api_token=api_token,
            grpc_port=grpc_port,
            flight_port=flight_port,
            object_store_endpoint=object_store_endpoint,
            object_store_access_key=object_store_access_key,
            object_store_secret_key=object_store_secret_key,
            object_store_region=object_store_region,
            patch_bucket=patch_bucket,
            review_bucket=review_bucket,
        )

    @staticmethod
    def _required(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(f"{name} is required")
        return value

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
