from __future__ import annotations

import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from starlette.types import Lifespan

from .repository import (
    SimulatorConflictError,
    SimulatorNotInitializedError,
    SimulatorRecordNotFoundError,
    SimulatorRepository,
    SimulatorStateError,
)
from .schemas import (
    AppendRecordsRequest,
    CreateInspectionRequest,
    InspectionKeyBody,
    InspectionResponse,
    PublicationResponse,
    PublishInspectionRequest,
    UpdateInspectionRequest,
)


def create_control_app(
    *,
    repository: SimulatorRepository,
    api_token: str,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    app = FastAPI(title="SC Upstream Simulator", version="0.1.0", lifespan=lifespan)

    async def authorize(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        expected = f"Bearer {api_token}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="valid simulator bearer token required",
            )

    control = APIRouter(
        prefix="/api/v1", dependencies=[Depends(authorize)], tags=["control"]
    )

    @app.exception_handler(SimulatorRecordNotFoundError)
    async def not_found_handler(
        _request: object, exc: SimulatorRecordNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(SimulatorConflictError)
    @app.exception_handler(SimulatorStateError)
    async def conflict_handler(
        _request: object, exc: SimulatorConflictError | SimulatorStateError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(SimulatorNotInitializedError)
    async def unavailable_handler(
        _request: object, exc: SimulatorNotInitializedError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid_value_handler(_request: object, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        await repository.check_ready()
        return {"status": "ready"}

    @control.post("/inspections", response_model=InspectionResponse, status_code=201)
    async def create_inspection(body: CreateInspectionRequest) -> InspectionResponse:
        key = await repository.create_draft(body.to_domain())
        return InspectionResponse.from_domain(await repository.get_inspection(key))

    @control.post("/inspections/records", status_code=204)
    async def append_records(body: AppendRecordsRequest) -> None:
        await repository.append_records(
            body.to_key(),
            defects=tuple(item.to_domain() for item in body.defects),
            review_images=tuple(item.to_domain() for item in body.review_images),
            patch_archives=tuple(item.to_domain() for item in body.patch_archives),
        )

    @control.post("/inspections/publish", response_model=PublicationResponse)
    async def publish_inspection(
        body: PublishInspectionRequest,
    ) -> PublicationResponse:
        publication = await repository.publish(
            body.to_key(), published_at=body.published_at
        )
        return PublicationResponse.from_domain(publication)

    @control.patch("/inspections", response_model=PublicationResponse)
    async def update_inspection(body: UpdateInspectionRequest) -> PublicationResponse:
        publication = await repository.update_published(
            body.to_key(), changed_at=body.changed_at, changes=body.changes()
        )
        return PublicationResponse.from_domain(publication)

    @control.get("/inspections", response_model=list[InspectionResponse])
    async def list_inspections(
        state_filter: Annotated[
            Literal["draft", "published"] | None, Query(alias="state")
        ] = None,
    ) -> list[InspectionResponse]:
        records = await repository.list_inspections(state=state_filter)
        return [InspectionResponse.from_domain(record) for record in records]

    @control.post("/inspections/inspect", response_model=InspectionResponse)
    async def inspect_inspection(body: InspectionKeyBody) -> InspectionResponse:
        return InspectionResponse.from_domain(
            await repository.get_inspection(body.to_key())
        )

    app.include_router(control)
    return app
