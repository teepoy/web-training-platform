from __future__ import annotations

from fastapi import APIRouter

from app.modules.agent.api.router import router as agent_router
from app.modules.auth.api.router import router as auth_router
from app.modules.classify.api.router import router as classify_router
from app.modules.dashboard.api.router import router as dashboard_router
from app.modules.datasets.api.extensions.import_parquet_router import (
    router as import_parquet_router,
)
from app.modules.datasets.api.extensions.export_parquet_router import (
    router as export_parquet_router,
)
from app.modules.datasets.api.router import router as datasets_router
from app.modules.models.api.router import router as models_router
from app.modules.preview.api.router import router as preview_router
from app.modules.prediction.api.router import router as prediction_router
from app.modules.schedules.api.router import router as schedules_router
from app.modules.sensors.api.router import router as sensors_router
from app.modules.task_tracker.api.router import router as task_tracker_router
from app.modules.training.api.router import router as training_router

MODULE_ROUTERS: list[APIRouter] = [
    import_parquet_router,
    export_parquet_router,
    datasets_router,
    agent_router,
    auth_router,
    classify_router,
    dashboard_router,
    models_router,
    preview_router,
    prediction_router,
    schedules_router,
    sensors_router,
    task_tracker_router,
    training_router,
]

EXTENSION_ROUTERS: list[APIRouter] = []
