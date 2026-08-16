from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.modules.sc.domain.entities.sc_import import ScImportStatus

ScImportProgressCallback = Callable[[ScImportStatus], Awaitable[None]]


class ScImportPort(Protocol):
    async def submit_upstream_import(
        self,
        source_inspection_time: str,
        source_wafer_key: int,
        dataset_name: str,
        org_id: str,
        created_by: str = "system",
        label_space: list[str] | None = None,
        max_rows: int | None = None,
        on_progress: ScImportProgressCallback | None = None,
    ) -> ScImportStatus: ...

    async def submit_import(
        self,
        source_inspection_time: str,
        source_wafer_key: int,
        image_source_profile: str,
        dataset_name: str,
        org_id: str,
        created_by: str = "system",
        label_space: list[str] | None = None,
        max_rows: int | None = None,
        on_progress: ScImportProgressCallback | None = None,
    ) -> ScImportStatus: ...


class ScPlotPointsPort(Protocol):
    async def ensure_plot_points_allowed(
        self, dataset_id: str, org_id: str
    ) -> None: ...

    async def build_plot_points_response(self, *args: Any, **kwargs: Any) -> Any: ...

    async def filter_dataset_box(self, *args: Any, **kwargs: Any) -> Any: ...


__all__ = ["ScImportPort", "ScPlotPointsPort"]
