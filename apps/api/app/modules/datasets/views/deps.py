from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.datasets.app.session import DatasetSessionFactory
from app.modules.datasets.domain.repository import DatasetRepository
from app.shared.injection import resolve


def get_dataset_session_factory(request: Request) -> DatasetSessionFactory:
    storage_factory = resolve(request, DatasetStorageFactoryPort)
    repo = resolve(request, DatasetRepository)
    return DatasetSessionFactory(
        repo=repo,
        storage_factory=storage_factory,
    )


DatasetSessionFactoryDep = Annotated[
    DatasetSessionFactory, Depends(get_dataset_session_factory)
]
