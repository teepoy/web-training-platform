from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from app.modules.sc.materialization.domain.sc_inspection import (
    ScInspectionMaterialization,
)


class ScInspectionMaterializerPort(Protocol):
    async def materialize(
        self,
        *,
        rows_lazyframe: Any,
        image_source_formats: Mapping[str, str],
        direct_dataset_id: str | None,
        dataset_id: str = "",
        job_id: str = "",
        image_types: list[str] | None = None,
        max_output_bytes: int,
    ) -> ScInspectionMaterialization: ...
