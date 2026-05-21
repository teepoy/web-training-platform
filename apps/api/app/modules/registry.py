from __future__ import annotations

from fastapi import APIRouter

from app.modules.agent.interfaces.controllers.router import router as agent_router
from app.modules.auth.interfaces.controllers.router import router as auth_router
from app.modules.classify.interfaces.controllers.router import router as classify_router
from app.modules.dashboard.interfaces.controllers.router import (
    router as dashboard_router,
)
from app.modules.datasets.interfaces.controllers.extensions.import_parquet_router import (
    router as import_parquet_router,
)
from app.modules.datasets.interfaces.controllers.extensions.export_parquet_router import (
    router as export_parquet_router,
)
from app.modules.datasets.interfaces.controllers.router import router as datasets_router
from app.modules.models.interfaces.controllers.router import router as models_router
from app.modules.preview.interfaces.controllers.router import router as preview_router
from app.modules.prediction.interfaces.controllers.router import (
    router as prediction_router,
)
from app.modules.schedules.interfaces.controllers.router import (
    router as schedules_router,
    runs_router,
)
from app.modules.sensors.interfaces.controllers.router import router as sensors_router
from app.modules.settings.interfaces.controllers.router import router as settings_router
from app.modules.task_tracker.interfaces.controllers.router import (
    router as task_tracker_router,
)
from app.modules.training.interfaces.controllers.router import router as training_router

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
    runs_router,
    sensors_router,
    settings_router,
    task_tracker_router,
    training_router,
]

EXTENSION_ROUTERS: list[APIRouter] = []
