from __future__ import annotations

from app.modules.runtime.domain.executables import RuntimeCapabilityCatalog
from app.modules.sc.runtime.descriptor import SC_RUNTIME_CAPABILITIES

runtime_capabilities = RuntimeCapabilityCatalog((SC_RUNTIME_CAPABILITIES,))

__all__ = ["runtime_capabilities"]
