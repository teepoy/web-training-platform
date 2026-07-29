from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.api.schemas import ArtifactRef
from app.shared.db.registry import ArtifactORM


class ArtifactSqlLookupRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_artifact(self, artifact_id: str) -> ArtifactRef | None:
        async with self._session_factory() as session:
            row = await session.get(ArtifactORM, artifact_id)
            if row is None:
                return None
            return ArtifactRef(
                id=row.id,
                uri=row.uri,
                kind=row.kind,
                metadata=row.metadata_json,
                name=row.name,
                file_size=row.file_size,
                file_hash=row.file_hash,
                format=row.format,
                created_at=row.created_at,
            )
