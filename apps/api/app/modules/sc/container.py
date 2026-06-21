from __future__ import annotations

from dataclasses import dataclass

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.sc.adapter import ScDatasetReader, ScDatasetStore
from app.modules.sc.adapter.batch_reader import ScBatchReader
from app.modules.sc.app.services.sc_plot_points_service import ScPlotPointsService
from app.modules.sc.app.services.sc_import_service import ScImportService
from app.modules.sc.domain.image_fetcher import ScImageFetcher
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.shared.context import SharedInfra
from app.shared.db.sql_repository import SqlRepository
from platform_runtime.sparse import DatasetPayloadStore


@dataclass
class ScContext:
    repository: SqlRepository
    dataset_store: ScDatasetStore
    image_fetcher: ScImageFetcher
    sc_import_service: ScImportService
    dataset_reader: ScDatasetReader
    upstream_reader: ScUpstreamReader
    batch_reader: ScBatchReader
    plot_points_service: ScPlotPointsService


def init_sc(
    shared: SharedInfra,
    dataset_reader: ScDatasetReader,
    dataset_payload_store: DatasetPayloadStore | None = None,
    upstream_reader: ScUpstreamReader | None = None,
    image_fetcher: ScImageFetcher | None = None,
    storage_factory: DatasetStorageFactory | None = None,
) -> ScContext:
    repository = SqlRepository(session_factory=shared.session_factory)
    batch_reader = ScBatchReader(async_engine=shared.db_engine)
    if dataset_payload_store is None:
        dataset_payload_store = DatasetPayloadStore(shared.artifact_storage)

    dataset_store = ScDatasetStore(
        dataset_payload_store=dataset_payload_store,
        batch_reader=batch_reader,
    )

    if upstream_reader is None:
        import os

        from app.modules.sc.adapter.grpc_upstream import GrpcScUpstream

        cfg = shared.config
        sc_cfg = getattr(cfg, "sc", None)
        upstream_cfg = getattr(sc_cfg, "upstream", None) if sc_cfg else None
        grpc_addr = (
            upstream_cfg.grpc_addr
            if upstream_cfg
            else os.environ.get("SC_UPSTREAM_ADDR", "sc-upstream:9091")
        )
        flight_addr = (
            upstream_cfg.flight_addr
            if upstream_cfg
            else os.environ.get("SC_UPSTREAM_FLIGHT_ADDR", "grpc://sc-upstream:9093")
        )
        upstream_reader = GrpcScUpstream(grpc_addr=grpc_addr, flight_addr=flight_addr)

    if image_fetcher is None:
        import os

        from app.modules.sc.adapter.grpc_image_fetcher import GrpcImageFetcher

        image_fetcher = GrpcImageFetcher(
            addr=os.environ.get("IMAGE_PARSER_GRPC_ADDR", "image-parser:9092")
        )

    svc = ScImportService(
        repository=repository,
        payload_store=dataset_payload_store,
        upstream_reader=upstream_reader,
        image_fetcher=image_fetcher,
    )

    if storage_factory is None:
        storage_factory = DatasetStorageFactory(
            repo=repository,
            storage=shared.artifact_storage,
            payload_store=dataset_payload_store,
            ls_client=shared.label_studio_client,
            session_factory=shared.session_factory,
        )

    plot_points_service = ScPlotPointsService(
        repository=repository,
        storage_factory=storage_factory,
    )

    return ScContext(
        repository=repository,
        dataset_store=dataset_store,
        image_fetcher=image_fetcher,
        sc_import_service=svc,
        dataset_reader=dataset_reader,
        upstream_reader=upstream_reader,
        batch_reader=batch_reader,
        plot_points_service=plot_points_service,
    )
