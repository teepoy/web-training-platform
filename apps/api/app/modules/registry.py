from __future__ import annotations

from fastapi import APIRouter

from app.modules.agent.port.http.router import router as agent_router
from app.modules.automations.port.http.router import router as automations_router
from app.modules.auth.port.http.router import router as auth_router
from app.modules.agent.classify.port.http.router import router as classify_router
from app.modules.dashboard.port.http.router import (
    router as dashboard_router,
)
from app.modules.dataset_collections.port.http.router import (
    router as dataset_collections_router,
)
from app.modules.datasets.port.http.extensions.import_parquet_router import (
    router as import_parquet_router,
)
from app.modules.datasets.port.http.extensions.export_parquet_router import (
    router as export_parquet_router,
)
from app.modules.datasets.port.http.extensions.prediction_router import (
    router as datasets_prediction_router,
)
from app.modules.datasets.port.http.router import router as datasets_router
from app.modules.models.port.http.router import router as models_router
from app.modules.prediction.port.http.router import (
    router as prediction_router,
)
from app.modules.sc.port.http.router import router as sc_router
from app.modules.sc.port.http.router import sc_datasets_router
from app.modules.sc.port.http.prediction_export_router import (
    router as sc_prediction_export_router,
)
from app.modules.jobs.schedules.port.http.router import (
    router as schedules_router,
    runs_router,
)
from app.modules.jobs.sensors.port.http.router import router as sensors_router
from app.core.settings.port.http.router import router as settings_router
from app.modules.jobs.task_tracker.port.http.router import (
    router as task_tracker_router,
)
from app.modules.training.port.http.router import router as training_router
from app.modules.source_discovery.port.http.router import (
    collections_router as source_discovery_collections_router,
    connectors_router as source_connectors_router,
    runs_router as source_discovery_runs_router,
)

MODULE_ROUTERS: list[APIRouter] = [
    import_parquet_router,
    export_parquet_router,
    datasets_prediction_router,
    datasets_router,
    dataset_collections_router,
    agent_router,
    automations_router,
    auth_router,
    classify_router,
    dashboard_router,
    models_router,
    prediction_router,
    schedules_router,
    runs_router,
    sensors_router,
    settings_router,
    task_tracker_router,
    training_router,
    sc_router,
    sc_datasets_router,
    sc_prediction_export_router,
    source_connectors_router,
    source_discovery_collections_router,
    source_discovery_runs_router,
]

EXTENSION_ROUTERS: list[APIRouter] = [
    # sc_router removed — already registered in MODULE_ROUTERS
]
