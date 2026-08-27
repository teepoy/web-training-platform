from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from sampling_rules import ReviewSamplingProgram

from app.modules.sc.domain.entities.sc_import import ScImportStatus
from app.modules.sc.domain.prediction_export import (
    ScKlarfVersion,
    ScPredictionExportFormat,
    ScPredictionExportResult,
    ScPredictionExportResultSource,
)

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


class ScPredictionExportPort(Protocol):
    async def export(
        self,
        *,
        dataset_id: str,
        org_id: str,
        created_by: str,
        export_format: ScPredictionExportFormat,
        result_source: ScPredictionExportResultSource,
        klarf_version: ScKlarfVersion,
        sample_filter: dict[str, object] | None,
        sampling_program: ReviewSamplingProgram | None,
        sampling_seed: int | None,
        sampling_extra_filter: dict[str, object] | None,
        include_images: bool,
    ) -> ScPredictionExportResult: ...

    async def export_collection(
        self,
        *,
        collection_id: str,
        member_ids: tuple[str, ...],
        org_id: str,
        created_by: str,
        export_format: ScPredictionExportFormat,
        result_source: ScPredictionExportResultSource,
        klarf_version: ScKlarfVersion,
        sample_filter: dict[str, object] | None,
        sampling_program: ReviewSamplingProgram | None,
        sampling_seed: int | None,
        sampling_extra_filter: dict[str, object] | None,
        include_images: bool,
    ) -> ScPredictionExportResult: ...


__all__ = ["ScImportPort", "ScPlotPointsPort", "ScPredictionExportPort"]
