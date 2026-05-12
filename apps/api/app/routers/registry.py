from __future__ import annotations

from fastapi import APIRouter

from app.routers.import_parquet.router import router as import_parquet_router
from app.routers.export_parquet.router import router as export_parquet_router

EXTENSION_ROUTERS: list[APIRouter] = [
    import_parquet_router,
    export_parquet_router,
]
