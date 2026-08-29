from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler

from omegaconf import OmegaConf

from app.core.logger import init_logging


def test_dev_logging_defaults_to_info() -> None:
    init_logging(
        OmegaConf.create({"app": {"env": "dev"}, "logging": {"level": "INFO"}})
    )

    root = logging.getLogger()
    assert root.level == logging.INFO
    assert all(handler.level == logging.INFO for handler in root.handlers)


def test_dev_logging_accepts_tracked_debug_level() -> None:
    init_logging(
        OmegaConf.create({"app": {"env": "dev"}, "logging": {"level": "DEBUG"}})
    )

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert all(handler.level == logging.DEBUG for handler in root.handlers)


def test_prod_logging_uses_json_console_without_file_handler(
    capsys,
) -> None:
    init_logging(
        OmegaConf.create({"app": {"env": "prod"}, "logging": {"level": "INFO"}})
    )

    root = logging.getLogger()
    assert root.level == logging.INFO
    assert not any(
        isinstance(handler, RotatingFileHandler) for handler in root.handlers
    )

    logging.getLogger("test.prod.logging").info("ship this to loki")

    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())
    assert payload["level"] == "info"
    assert payload["service"] == "api"
    assert payload["env"] == "prod"
    assert payload["logger"] == "test.prod.logging"
    assert payload["message"] == "ship this to loki"


def test_prod_json_logging_includes_extra_fields(
    capsys,
) -> None:
    init_logging(
        OmegaConf.create({"app": {"env": "prod"}, "logging": {"level": "INFO"}})
    )

    logging.getLogger("test.prod.auth").info(
        "user logged in",
        extra={
            "event": "auth.user_login",
            "user_id": "user-123",
            "login_date_utc": "2026-07-05",
        },
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())
    assert payload["event"] == "auth.user_login"
    assert payload["user_id"] == "user-123"
    assert payload["login_date_utc"] == "2026-07-05"
