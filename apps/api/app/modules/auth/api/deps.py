from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_session_factory(
    request: Request,
) -> async_sessionmaker[AsyncSession]:
    return request.app.state.container.session_factory


SessionFactory = Annotated[
    async_sessionmaker[AsyncSession], Depends(get_session_factory)
]
