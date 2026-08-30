from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.dataset_collections.port.local import (
    CollectionModelManagementPort,
    CollectionRevisionPublishingPort,
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


def get_collection_model_management(
    request: Request,
) -> CollectionModelManagementPort:
    return resolve(request, CollectionModelManagementPort)


CollectionModelManagementDep = Annotated[
    CollectionModelManagementPort, Depends(get_collection_model_management)
]


def get_collection_revision_publishing(
    request: Request,
) -> CollectionRevisionPublishingPort:
    return resolve(request, CollectionRevisionPublishingPort)


CollectionRevisionPublishingDep = Annotated[
    CollectionRevisionPublishingPort,
    Depends(get_collection_revision_publishing),
]
