from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from app.modules.runtime.domain.events import (
    ArtifactOutput,
    LocalArtifactFile,
    StoredArtifact,
)
from app.modules.training.domain.repository import TrainingRepository
from app.shared.api.schemas import ArtifactRef
from app.shared.domain.protocols import ArtifactStorage


@dataclass(frozen=True, slots=True)
class PlatformArtifactOutputSink:
    """Upload and record artifacts while consuming a runtime event stream."""

    storage: ArtifactStorage
    repository: TrainingRepository
    job_id: str

    async def persist(self, output: ArtifactOutput) -> ArtifactRef:
        payload = output.payload
        match payload:
            case LocalArtifactFile(
                path=path,
                object_name=object_name,
                content_type=content_type,
            ):
                file_size = await asyncio.to_thread(_file_size, path)
                uri = await self.storage.put_file(
                    object_name=object_name,
                    path=str(path),
                    content_type=content_type,
                )
            case StoredArtifact(uri=uri):
                file_size = None
            case _:
                assert_never(payload)

        artifact = ArtifactRef(
            id=output.id,
            uri=uri,
            kind=output.kind,
            metadata=dict(output.metadata),
            name=output.name,
            file_size=file_size,
            format=output.format,
        )
        await self.repository.upsert_artifacts(self.job_id, [artifact])
        return artifact


def _file_size(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError(f"Runtime artifact file does not exist: {path}")
    return path.stat().st_size


__all__ = ["PlatformArtifactOutputSink"]
