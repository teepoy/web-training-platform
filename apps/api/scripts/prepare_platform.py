from __future__ import annotations

import asyncio

import app.registrations as _registrations  # noqa: F401
from app.core.config import load_config
from app.core.logger import init_logging
from app.core.platform_setup import prepare_platform


def main() -> None:
    config = load_config()
    init_logging(config)
    asyncio.run(prepare_platform(config))


if __name__ == "__main__":
    main()
