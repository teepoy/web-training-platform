from __future__ import annotations

import json
import logging
import logging.config
import os
from datetime import UTC, datetime
from typing import Any

from omegaconf import DictConfig

from app.core.config import AppConfig, _as_app_config

_LOG_RECORD_BUILTINS = frozenset(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
)


class JsonLogFormatter(logging.Formatter):
    def __init__(self, *, env: str, service: str) -> None:
        super().__init__()
        self._env = env
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self._service,
            "env": self._env,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            error_type = record.exc_info[0]
            if error_type is not None:
                payload["error_type"] = error_type.__name__
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _LOG_RECORD_BUILTINS and key not in payload:
                payload[key] = self._json_safe(value)
        return json.dumps(payload, ensure_ascii=False)

    def _json_safe(self, value: object) -> object:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, list | tuple):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        return str(value)


def init_logging(cfg: AppConfig | DictConfig) -> None:
    cfg = _as_app_config(cfg)
    env = str(cfg.app.env)
    log_level_override = os.getenv("LOG_LEVEL", "").upper()

    if env == "test":
        level = log_level_override or "WARNING"
    elif env == "dev":
        level = log_level_override or "INFO"
    else:
        level = log_level_override or "WARNING"

    log_cfg_value = cfg.get("logging", {}) or {}
    log_cfg = log_cfg_value if isinstance(log_cfg_value, dict) else {}

    config: dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": log_cfg.get(
                    "format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
                ),
            },
            "brief": {
                "format": "%(asctime)s [%(levelname)s] %(message)s",
            },
            "json": {
                "()": JsonLogFormatter,
                "env": env,
                "service": "api",
            },
        },
        "handlers": {},
        "root": {"level": level, "handlers": []},
    }

    if env == "prod":
        config["handlers"] = {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "json",
            },
        }
        config["root"]["handlers"] = ["console"]
    else:
        config["handlers"] = {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "detailed",
            },
        }
        config["root"]["handlers"] = ["console"]

    logging.config.dictConfig(config)
