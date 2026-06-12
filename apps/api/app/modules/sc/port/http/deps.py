from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.sc.adapter import ScDatasetReader, ScDatasetStore
from app.modules.sc.app.services.sc_import_service import ScImportService
from app.modules.sc.app.services.sc_plot_points_service import ScPlotPointsService
from app.modules.sc.app.services.sprite_service import SpriteService
from app.modules.sc.domain.image_fetcher import ScImageFetcher
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.shared.infrastructure.prefect.client import PrefectClient
from platform_runtime.sparse import DatasetPayloadStore


def get_sc_import_service(request: Request) -> ScImportService:
    return request.app.state.app_context.sc.sc_import_service


def get_image_fetcher(request: Request) -> ScImageFetcher:
    return request.app.state.app_context.sc.image_fetcher


def get_prefect_client(request: Request) -> PrefectClient:
    return request.app.state.app_context.shared.prefect_client


def get_upstream_reader(request: Request) -> ScUpstreamReader:
    return request.app.state.app_context.sc.upstream_reader


def get_sprite_service(request: Request) -> SpriteService:
    return request.app.state.app_context.sc.sprite_service


def get_sc_plot_points_service(request: Request) -> ScPlotPointsService:
    return request.app.state.app_context.sc.plot_points_service


def get_dataset_payload_store(request: Request) -> DatasetPayloadStore:
    return request.app.state.app_context.datasets.dataset_payload_store


def get_sc_dataset_reader(request: Request) -> ScDatasetReader:
    return request.app.state.app_context.sc.dataset_reader


def get_sc_dataset_store(request: Request) -> ScDatasetStore:
    return request.app.state.app_context.sc.dataset_store


ScImportServiceDep = Annotated[ScImportService, Depends(get_sc_import_service)]
ScImageFetcherDep = Annotated[ScImageFetcher, Depends(get_image_fetcher)]
PrefectClientDep = Annotated[PrefectClient, Depends(get_prefect_client)]
ScUpstreamReaderDep = Annotated[ScUpstreamReader, Depends(get_upstream_reader)]
ScSpriteServiceDep = Annotated[SpriteService, Depends(get_sprite_service)]
ScPlotPointsServiceDep = Annotated[
    ScPlotPointsService, Depends(get_sc_plot_points_service)
]
DatasetPayloadStoreDep = Annotated[
    DatasetPayloadStore, Depends(get_dataset_payload_store)
]
ScDatasetReaderDep = Annotated[ScDatasetReader, Depends(get_sc_dataset_reader)]
ScDatasetStoreDep = Annotated[ScDatasetStore, Depends(get_sc_dataset_store)]
