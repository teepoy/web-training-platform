from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler

from omegaconf import OmegaConf

from app.core.logger import init_logging


def test_prod_logging_uses_json_console_without_file_handler(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    init_logging(OmegaConf.create({"app": {"env": "prod"}}))

    root = logging.getLogger()
    assert root.level == logging.INFO
    assert not any(isinstance(handler, RotatingFileHandler) for handler in root.handlers)

    logging.getLogger("test.prod.logging").info("ship this to loki")

    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())
    assert payload["level"] == "info"
    assert payload["service"] == "api"
    assert payload["env"] == "prod"
    assert payload["logger"] == "test.prod.logging"
    assert payload["message"] == "ship this to loki"
