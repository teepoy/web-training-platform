from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.sc.adapter.batch_reader import ScBatchReader
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.sc.port.local import (
    ScImportPort,
    ScPlotPointsPort,
    ScPredictionExportPort,
)
from app.shared.domain.protocols import PrefectClient
from app.shared.injection import resolve


def get_sc_import_service(request: Request) -> ScImportPort:
    return resolve(request, ScImportPort)


def get_prefect_client(request: Request) -> PrefectClient:
    return resolve(request, PrefectClient)


def get_upstream_reader(request: Request) -> ScUpstreamReader:
    return resolve(request, ScUpstreamReader)


def get_sc_plot_points_service(request: Request) -> ScPlotPointsPort:
    return resolve(request, ScPlotPointsPort)


def get_sc_prediction_export_service(request: Request) -> ScPredictionExportPort:
    return resolve(request, ScPredictionExportPort)


def get_sc_batch_reader(request: Request) -> ScBatchReader:
    return resolve(request, ScBatchReader)


ScImportServiceDep = Annotated[ScImportPort, Depends(get_sc_import_service)]
PrefectClientDep = Annotated[PrefectClient, Depends(get_prefect_client)]
ScUpstreamReaderDep = Annotated[ScUpstreamReader, Depends(get_upstream_reader)]
ScPlotPointsServiceDep = Annotated[
    ScPlotPointsPort, Depends(get_sc_plot_points_service)
]
ScBatchReaderDep = Annotated[ScBatchReader, Depends(get_sc_batch_reader)]
ScPredictionExportDep = Annotated[
    ScPredictionExportPort, Depends(get_sc_prediction_export_service)
]
