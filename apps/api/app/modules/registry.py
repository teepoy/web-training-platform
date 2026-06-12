from __future__ import annotations

from fastapi import APIRouter

from app.modules.agent.port.http.router import router as agent_router
from app.modules.auth.port.http.router import router as auth_router
from app.modules.classify.port.http.router import router as classify_router
from app.modules.dashboard.port.http.router import (
    router as dashboard_router,
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
from app.modules.preview.port.http.router import router as preview_router
from app.modules.prediction.port.http.router import (
    router as prediction_router,
)
from app.modules.sc.port.http.router import router as sc_router
from app.modules.sc.port.http.router import sc_datasets_router
from app.modules.schedules.port.http.router import (
    router as schedules_router,
    runs_router,
)
from app.modules.sensors.port.http.router import router as sensors_router
from app.modules.settings.port.http.router import router as settings_router
from app.modules.task_tracker.port.http.router import (
    router as task_tracker_router,
)
from app.modules.training.port.http.router import router as training_router

MODULE_ROUTERS: list[APIRouter] = [
    import_parquet_router,
    export_parquet_router,
    datasets_prediction_router,
    datasets_router,
    agent_router,
    auth_router,
    classify_router,
    dashboard_router,
    models_router,
    preview_router,
    prediction_router,
    schedules_router,
    runs_router,
    sensors_router,
    settings_router,
    task_tracker_router,
    training_router,
    sc_router,
    sc_datasets_router,
]

EXTENSION_ROUTERS: list[APIRouter] = [
    # sc_router removed — already registered in MODULE_ROUTERS
]
