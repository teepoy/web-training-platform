from __future__ import annotations

from app.modules.runtime.domain.executables import RuntimeCapabilityCatalog
from app.modules.sc.runtime.registration import SC_RUNTIME_ROUTER
from app.modules.types.catalog import list_views

runtime_catalog = RuntimeCapabilityCatalog(
    (SC_RUNTIME_ROUTER,),
    known_views={view.id: view.ref for view in list_views()},
)

__all__ = ["runtime_catalog"]
