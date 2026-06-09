from __future__ import annotations

import logging.config
import os

from omegaconf import DictConfig


def init_logging(cfg: DictConfig) -> None:
    env = str(cfg.app.env)
    log_level_override = os.getenv("LOG_LEVEL", "").upper()

    if env == "test":
        level = log_level_override or "WARNING"
    elif env == "dev":
        level = log_level_override or "INFO"
    else:
        level = log_level_override or "WARNING"

    log_cfg = cfg.get("logging", {})

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
        },
        "handlers": {},
        "root": {"level": level, "handlers": []},
    }

    if env == "prod":
        log_dir = str(log_cfg.get("file_dir", "logs"))
        filename = str(log_cfg.get("filename", "app.log"))
        max_bytes = int(log_cfg.get("max_bytes", 10 * 1024 * 1024))
        backup_count = int(log_cfg.get("backup_count", 5))

        config["handlers"] = {
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": level,
                "formatter": "detailed",
                "filename": f"{log_dir}/{filename}",
                "maxBytes": max_bytes,
                "backupCount": backup_count,
            },
            "console": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
                "formatter": "brief",
            },
        }
        config["root"]["handlers"] = ["file", "console"]
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
