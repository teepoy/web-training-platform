"""Entrypoint shim preserved for worker Docker CMD + Prefect infra deployment specs.

Do NOT add new logic here — flows live in
``app.modules.<x>.infrastructure.flows.*``.
"""

from __future__ import annotations

import asyncio
import os

from app.shared.infrastructure.prefect.flow_serve import main, main_v2

if __name__ == "__main__":
    mode = os.getenv("WORKER_MODE", "v1").lower()
    if mode == "v2":
        asyncio.run(main_v2())
    else:
        asyncio.run(main())
