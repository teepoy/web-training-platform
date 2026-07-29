from __future__ import annotations

from typing import Any, Protocol

from app.modules.sc.materialization.domain.sc_inspection import (
    ScInspectionMaterialization,
)


class ScInspectionMaterializerPort(Protocol):
    async def materialize(
        self,
        *,
        rows_lazyframe: Any,
        dataset_id: str = "",
        job_id: str = "",
        image_types: list[str] | None = None,
    ) -> ScInspectionMaterialization: ...
