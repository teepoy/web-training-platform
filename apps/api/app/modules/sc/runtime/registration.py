from __future__ import annotations

import app.modules.sc.runtime.predictors  # noqa: F401
import app.modules.sc.runtime.trainers  # noqa: F401
import app.modules.sc.runtime.workflows  # noqa: F401
from app.modules.sc.runtime.router import SC_RUNTIME_ROUTER

__all__ = ["SC_RUNTIME_ROUTER"]
