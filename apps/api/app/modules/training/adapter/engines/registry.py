from __future__ import annotations

from collections.abc import Callable

from app.shared.domain.protocols import ArtifactStorage, TrainingExecutionEngine

TrainingEngineFactory = Callable[[ArtifactStorage], TrainingExecutionEngine]
_EXTERNAL_FACTORIES: dict[str, TrainingEngineFactory] = {}


def register_training_engine_factory(kind: str, factory: TrainingEngineFactory) -> None:
    """Register a non-production engine from an external composition root."""
    if not kind or kind in {"prefect", "kubeflow"}:
        raise ValueError("external engine kind conflicts with a production engine")
    _EXTERNAL_FACTORIES[kind] = factory


def build_registered_training_engine(
    kind: str, storage: ArtifactStorage
) -> TrainingExecutionEngine:
    factory = _EXTERNAL_FACTORIES.get(kind)
    if factory is None:
        raise RuntimeError(
            f"No training execution adapter registered for engine: {kind}"
        )
    return factory(storage)
