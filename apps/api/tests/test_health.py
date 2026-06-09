from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}
        assert "auth_enabled" not in res.json()


def test_readiness() -> None:
    with TestClient(app) as client:
        res = client.get("/ready")
        assert res.status_code == 200
        assert res.json() == {"status": "ready"}


def test_readiness_returns_503_when_database_is_unavailable(monkeypatch) -> None:
    with TestClient(app) as client:
        engine = app.state.app_context.shared.db_engine
        connection_context = MagicMock()
        connection_context.__aenter__ = AsyncMock(
            side_effect=RuntimeError("database unavailable")
        )
        connection_context.__aexit__ = AsyncMock(return_value=None)
        monkeypatch.setattr(
            type(engine),
            "connect",
            MagicMock(return_value=connection_context),
        )

        res = client.get("/ready")

        assert res.status_code == 503
        assert res.json() == {"status": "unavailable"}
