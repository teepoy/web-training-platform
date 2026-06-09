from __future__ import annotations

from dataclasses import dataclass

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.sc.adapter import ScDatasetReader, ScDatasetStore
from app.modules.sc.adapter.batch_reader import ScBatchReader
from app.modules.sc.app.services.sc_plot_points_service import ScPlotPointsService
from app.modules.sc.app.services.sc_import_service import ScImportService
from app.modules.sc.app.services.sprite_service import SpriteService
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
    sprite_service: SpriteService
    plot_points_service: ScPlotPointsService


def init_sc(
    shared: SharedInfra,
    dataset_reader: ScDatasetReader,
    dataset_payload_store: DatasetPayloadStore | None = None,
    upstream_reader: ScUpstreamReader | None = None,
    image_fetcher: ScImageFetcher | None = None,
    storage_factory: DatasetStorageFactory | None = None,
) -> ScContext:
    """Create ScContext with explicit upstream and image fetcher ports.

    The composition root (composition.py) provides concrete implementations.
    For dev/test, use the mock adapters in ``app.modules.sc.adapter._wafer_mock``.
    """
    repository = SqlRepository(session_factory=shared.session_factory)
    batch_reader = ScBatchReader(async_engine=shared.db_engine)
    if dataset_payload_store is None:
        dataset_payload_store = DatasetPayloadStore(shared.artifact_storage)

    dataset_store = ScDatasetStore(
        dataset_payload_store=dataset_payload_store,
        batch_reader=batch_reader,
    )

    if upstream_reader is None:
        from app.modules.sc.adapter._wafer_mock.sqlite_upstream import SqliteScUpstream

        cfg = shared.config
        sc_cfg = getattr(cfg, "sc", None)
        mock_cfg = getattr(sc_cfg, "mock", None) if sc_cfg else None
        db_url = mock_cfg.db_url if mock_cfg else "sqlite:///./wafer_inspection.db"
        upstream_reader = SqliteScUpstream(db_url=db_url)

    if image_fetcher is None:
        from app.modules.sc.adapter._wafer_mock import PatchImageCache
        from app.modules.sc.adapter._wafer_mock.image_service import ScImageService

        cfg = shared.config
        _data_dir = str(cfg.data.dir) if cfg.data.dir else None
        redis_cfg = getattr(cfg, "redis", None)
        if redis_cfg is not None and getattr(redis_cfg, "enabled", False):
            import redis as _redis

            from app.modules.sc.adapter._wafer_mock.redis_cache import (
                RedisPatchImageCache,
            )

            _host = getattr(redis_cfg, "host", "localhost")
            _port = int(getattr(redis_cfg, "port", 6379))
            _password = getattr(redis_cfg, "password", "") or None
            _db = int(getattr(redis_cfg, "db", 0))
            _client = _redis.Redis(host=_host, port=_port, password=_password, db=_db)
            image_cache = RedisPatchImageCache(redis_client=_client)
        else:
            image_cache = PatchImageCache(data_dir=_data_dir)

        image_fetcher = ScImageService(cache=image_cache)

    svc = ScImportService(
        prefect_client=shared.prefect_client,
        repository=repository,
        payload_store=dataset_payload_store,
        upstream_reader=upstream_reader,
        image_fetcher=image_fetcher,
    )

    sprite_service = SpriteService(image_fetcher=image_fetcher)

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
        sprite_service=sprite_service,
        plot_points_service=plot_points_service,
    )
