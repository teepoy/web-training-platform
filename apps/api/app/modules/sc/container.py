from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from injector import Module, inject, provider, singleton
from app.modules.storage.domain.sparse import DatasetPayloadStore

from app.modules.dataset_collections.port.local import CollectionExportReaderPort
from app.modules.storage.port.local import (
    DataPlaneSchemaRegistryPort,
    DatasetStorageFactoryPort,
    SparseImportWriterFactoryPort,
)
from app.modules.storage.domain.data_plane import DataPlaneSchemaRegistry
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.datasets.port.local import DatasetRevisionPublisherPort
from app.modules.sc.adapter.batch_reader import ScBatchReader
from app.modules.sc.adapter.grpc_job_image_stream import (
    GrpcJobImageStreamFactory,
    ScImageStreamUseCase,
)
from app.modules.sc.app.services.sc_plot_points_service import ScPlotPointsService
from app.modules.sc.app.services.sc_import_service import ScImportService
from app.modules.sc.app.services.prediction_export_service import (
    ScPredictionExportService,
)
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.sc.materialization.app.services.sc_inspection_materializer import (
    ScInspectionMaterializer,
)
from app.modules.sc.domain.image_stream import (
    ScExportImageStreamFactory,
    ScPredictionImageStreamFactory,
    ScTrainingImageStreamFactory,
)
from app.modules.sc.materialization.port.local import ScInspectionMaterializerPort
from app.modules.sc.port.local import (
    ScImportPort,
    ScPlotPointsPort,
    ScPredictionExportPort,
)
from app.shared.context import SharedInfra


@dataclass
class ScContext:
    sc_import_service: ScImportService
    upstream_reader: ScUpstreamReader
    batch_reader: ScBatchReader
    plot_points_service: ScPlotPointsService
    sc_inspection_materializer: ScInspectionMaterializer
    prediction_image_stream_factory: ScPredictionImageStreamFactory
    training_image_stream_factory: ScTrainingImageStreamFactory
    export_image_stream_factory: ScExportImageStreamFactory
    prediction_export_service: ScPredictionExportService


def init_sc(
    shared: SharedInfra,
    dataset_repository: DatasetRepository,
    storage_factory: DatasetStorageFactoryPort,
    sparse_import_factory: SparseImportWriterFactoryPort,
    schema_registry: DataPlaneSchemaRegistry,
    revision_publisher: DatasetRevisionPublisherPort,
    collection_reader: CollectionExportReaderPort,
    dataset_payload_store: DatasetPayloadStore | None = None,
    upstream_reader: ScUpstreamReader | None = None,
    prediction_image_stream_factory: ScPredictionImageStreamFactory | None = None,
    training_image_stream_factory: ScTrainingImageStreamFactory | None = None,
    export_image_stream_factory: ScExportImageStreamFactory | None = None,
) -> ScContext:
    repository = dataset_repository
    batch_reader = ScBatchReader(async_engine=shared.db_engine)
    if dataset_payload_store is None:
        dataset_payload_store = DatasetPayloadStore(
            shared.artifact_storage,
            manifest_cache_max_bytes=(
                shared.config.storage.sparse_manifest_cache_max_bytes
            ),
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

    import os

    image_parser_addr = os.environ.get("IMAGE_PARSER_GRPC_ADDR", "image-parser:9092")
    if prediction_image_stream_factory is None:
        prediction_image_stream_factory = GrpcJobImageStreamFactory(
            addr=image_parser_addr,
            use_case=ScImageStreamUseCase.PREDICTION,
        )
    if training_image_stream_factory is None:
        training_image_stream_factory = GrpcJobImageStreamFactory(
            addr=image_parser_addr,
            use_case=ScImageStreamUseCase.TRAINING,
        )
    if export_image_stream_factory is None:
        export_image_stream_factory = GrpcJobImageStreamFactory(
            addr=image_parser_addr,
            use_case=ScImageStreamUseCase.EXPORT,
        )

    svc = ScImportService(
        repository=repository,
        payload_store=dataset_payload_store,
        revision_publisher=revision_publisher,
        upstream_reader=upstream_reader,
        sparse_import_factory=sparse_import_factory,
        import_batch_rows=shared.config.sc.pipeline.import_batch_rows,
        index_row_group_rows=shared.config.sc.pipeline.index_row_group_rows,
    )

    plot_points_service = ScPlotPointsService(
        repository=repository,
        storage_factory=storage_factory,
    )
    sc_inspection_materializer = ScInspectionMaterializer(
        image_stream_factory=training_image_stream_factory,
        schema_registry=schema_registry,
        batch_rows=shared.config.sc.pipeline.materialization_batch_rows,
        max_error_records=(shared.config.sc.pipeline.materialization_max_error_records),
    )
    prediction_export_service = ScPredictionExportService(
        repository=repository,
        collection_reader=collection_reader,
        storage_factory=storage_factory,
        artifact_storage=shared.artifact_storage,
        image_stream_factory=export_image_stream_factory,
        image_batch_rows=shared.config.sc.pipeline.prediction_input_batch_rows,
    )

    return ScContext(
        sc_import_service=svc,
        upstream_reader=upstream_reader,
        batch_reader=batch_reader,
        plot_points_service=plot_points_service,
        sc_inspection_materializer=sc_inspection_materializer,
        prediction_image_stream_factory=prediction_image_stream_factory,
        training_image_stream_factory=training_image_stream_factory,
        export_image_stream_factory=export_image_stream_factory,
        prediction_export_service=prediction_export_service,
    )


class ScModule(Module):
    @inject
    @provider
    @singleton
    def provide_sc_context(
        self,
        shared: SharedInfra,
        dataset_repository: DatasetRepository,
        dataset_payload_store: DatasetPayloadStore,
        storage_factory: DatasetStorageFactoryPort,
        sparse_import_factory: SparseImportWriterFactoryPort,
        schema_registry: DataPlaneSchemaRegistryPort,
        revision_publisher: DatasetRevisionPublisherPort,
        collection_reader: CollectionExportReaderPort,
    ) -> ScContext:
        return init_sc(
            shared,
            dataset_repository=dataset_repository,
            dataset_payload_store=dataset_payload_store,
            storage_factory=storage_factory,
            sparse_import_factory=sparse_import_factory,
            schema_registry=cast(DataPlaneSchemaRegistry, schema_registry),
            revision_publisher=revision_publisher,
            collection_reader=collection_reader,
        )

    @provider
    @singleton
    def provide_sc_import_service(self, context: ScContext) -> ScImportService:
        return context.sc_import_service

    @provider
    @singleton
    def provide_sc_import_port(self, service: ScImportService) -> ScImportPort:
        return service

    @provider
    @singleton
    def provide_sc_plot_points_service(self, context: ScContext) -> ScPlotPointsService:
        return context.plot_points_service

    @provider
    @singleton
    def provide_sc_plot_points_port(
        self, service: ScPlotPointsService
    ) -> ScPlotPointsPort:
        return service

    @provider
    @singleton
    def provide_sc_batch_reader(self, context: ScContext) -> ScBatchReader:
        return context.batch_reader

    @provider
    @singleton
    def provide_sc_upstream_reader(self, context: ScContext) -> ScUpstreamReader:
        return context.upstream_reader

    @provider
    @singleton
    def provide_sc_inspection_materializer(
        self, context: ScContext
    ) -> ScInspectionMaterializerPort:
        return context.sc_inspection_materializer

    @provider
    @singleton
    def provide_sc_prediction_image_stream_factory(
        self, context: ScContext
    ) -> ScPredictionImageStreamFactory:
        return context.prediction_image_stream_factory

    @provider
    @singleton
    def provide_sc_training_image_stream_factory(
        self, context: ScContext
    ) -> ScTrainingImageStreamFactory:
        return context.training_image_stream_factory

    @provider
    @singleton
    def provide_sc_export_image_stream_factory(
        self, context: ScContext
    ) -> ScExportImageStreamFactory:
        return context.export_image_stream_factory

    @provider
    @singleton
    def provide_sc_prediction_export_service(
        self, context: ScContext
    ) -> ScPredictionExportService:
        return context.prediction_export_service

    @provider
    @singleton
    def provide_sc_prediction_export_port(
        self, service: ScPredictionExportService
    ) -> ScPredictionExportPort:
        return service
