from __future__ import annotations

from fastapi import APIRouter

from app.routers.import_parquet.router import router as import_parquet_router
from app.routers.export_parquet.router import router as export_parquet_router

from app.routers.datasets.router import router as datasets_router
from app.routers.jobs.router import router as jobs_router
from app.routers.models.router import router as models_router
from app.routers.auth.router import router as auth_router
from app.routers.schedules.router import router as schedules_router
from app.routers.preview.router import router as preview_router
from app.routers.agent.router import router as agent_router
from app.routers.task_tracker.router import router as task_tracker_router

EXTENSION_ROUTERS: list[APIRouter] = [
    import_parquet_router,
    export_parquet_router,
]

DOMAIN_ROUTERS: list[APIRouter] = [
    datasets_router,
    jobs_router,
    models_router,
    auth_router,
    schedules_router,
    preview_router,
    agent_router,
    task_tracker_router,
]
