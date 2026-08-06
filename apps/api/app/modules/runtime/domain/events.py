from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import TypeAlias, assert_never

from app.shared.api.schemas import ArtifactRef


@dataclass(frozen=True, slots=True)
class ArtifactProduced:
    artifact: ArtifactRef


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
    ArtifactProduced
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


async def collect_runtime_events(events: RuntimeEventStream) -> dict[str, object]:
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
            case ArtifactProduced(artifact=artifact):
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
    "ArtifactProduced",
    "MetricsReported",
    "OperationCompleted",
    "ProgressReported",
    "RuntimeEvent",
    "RuntimeEventStream",
    "RuntimeExecutionError",
    "RuntimeIssueReported",
    "collect_runtime_events",
]
