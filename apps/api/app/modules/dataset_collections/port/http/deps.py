from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.dataset_collections.port.local import (
    DatasetCollectionManagementPort,
)
from app.shared.injection import resolve


def get_dataset_collection_service(
    request: Request,
) -> DatasetCollectionManagementPort:
    return resolve(request, DatasetCollectionManagementPort)


DatasetCollectionServiceDep = Annotated[
    DatasetCollectionManagementPort, Depends(get_dataset_collection_service)
]
