from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.datasets.app.session import DatasetSessionFactory
from app.modules.datasets.domain.repository import DatasetRepository


def get_dataset_session_factory(request: Request) -> DatasetSessionFactory:
    ctx = request.app.state.app_context
    storage_factory: DatasetStorageFactory = ctx.datasets.dataset_storage_factory
    repo: DatasetRepository = ctx.datasets.dataset_repository
    return DatasetSessionFactory(
        repo=repo,
        storage_factory=storage_factory,
    )


DatasetSessionFactoryDep = Annotated[
    DatasetSessionFactory, Depends(get_dataset_session_factory)
]
