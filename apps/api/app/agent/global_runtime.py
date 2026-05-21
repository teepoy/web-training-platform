"""Thin shim — re-exports from canonical module.

All substantive code lives in
``app.modules.agent.application.services.global_runtime``.
"""

from __future__ import annotations

from app.modules.agent.application.services.global_runtime import GlobalAgent  # noqa: F401
from app.shared.infrastructure.llm.client import call_llm as _call_llm  # noqa: F401
