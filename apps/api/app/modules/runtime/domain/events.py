from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TypeAlias, assert_never

from app.shared.api.schemas import ArtifactRef


@dataclass(frozen=True, slots=True)
class LocalArtifactFile:
    path: Path
    object_name: str
    content_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        if not self.object_name:
            raise ValueError("Artifact object_name must not be empty")


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    uri: str

    def __post_init__(self) -> None:
        if not self.uri:
            raise ValueError("Artifact URI must not be empty")


ArtifactPayload: TypeAlias = LocalArtifactFile | StoredArtifact


@dataclass(frozen=True, slots=True)
class ArtifactOutput:
    id: str
    kind: str
    payload: ArtifactPayload
    metadata: Mapping[str, object] = field(default_factory=dict)
    name: str | None = None
    format: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Artifact id must not be empty")
        if not self.kind:
            raise ValueError("Artifact kind must not be empty")


class ArtifactOutputSink(Protocol):
    async def persist(self, output: ArtifactOutput) -> ArtifactRef: ...


@dataclass(frozen=True, slots=True)
class MetricsReported:
    metrics: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ProgressReported:
    current: int
    total: int | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeIssueReported:
    code: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OperationCompleted:
    summary: Mapping[str, object] = field(default_factory=dict)


RuntimeEvent: TypeAlias = (
    ArtifactOutput
    | MetricsReported
    | ProgressReported
    | RuntimeIssueReported
    | OperationCompleted
)
RuntimeEventStream: TypeAlias = AsyncIterator[RuntimeEvent]


class RuntimeExecutionError(RuntimeError):
    """Expected fatal error raised deliberately by a runtime callable."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


async def collect_runtime_events(
    events: RuntimeEventStream,
    *,
    artifact_sink: ArtifactOutputSink | None = None,
) -> dict[str, object]:
    """Consume one runtime stream and build its transport-safe terminal result."""

    artifacts: list[dict[str, object]] = []
    metrics: dict[str, object] = {}
    progress: list[dict[str, object]] = []
    issues: list[dict[str, object]] = []
    completion: OperationCompleted | None = None

    async for event in events:
        if completion is not None:
            raise RuntimeError("Runtime callable emitted an event after completion")
        match event:
            case ArtifactOutput() as output:
                if artifact_sink is None:
                    raise RuntimeError(
                        "Runtime callable emitted ArtifactOutput without an artifact sink"
                    )
                artifact = await artifact_sink.persist(output)
                artifacts.append(artifact.model_dump(mode="json"))
            case MetricsReported(metrics=reported):
                metrics.update(reported)
            case ProgressReported(current=current, total=total, message=message):
                item: dict[str, object] = {"current": current}
                if total is not None:
                    item["total"] = total
                if message is not None:
                    item["message"] = message
                progress.append(item)
            case RuntimeIssueReported(code=code, message=message, details=details):
                issues.append(
                    {"code": code, "message": message, "details": dict(details)}
                )
            case OperationCompleted():
                completion = event
            case _:
                assert_never(event)

    if completion is None:
        raise RuntimeError("Runtime callable completed without OperationCompleted")

    result = dict(completion.summary)
    if artifacts:
        result["artifacts"] = artifacts
    if metrics:
        result["metrics"] = metrics
    if progress:
        result["progress"] = progress
    if issues:
        result["issues"] = issues
    return result


__all__ = [
    "ArtifactOutput",
    "ArtifactOutputSink",
    "ArtifactPayload",
    "LocalArtifactFile",
    "MetricsReported",
    "OperationCompleted",
    "ProgressReported",
    "RuntimeEvent",
    "RuntimeEventStream",
    "RuntimeExecutionError",
    "RuntimeIssueReported",
    "StoredArtifact",
    "collect_runtime_events",
]
