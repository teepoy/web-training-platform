from __future__ import annotations

from app.core.registry import Trainer
from app.core.registry import get_trainer as get_registered_trainer
from app.core.registry import trainer
from app.runtime_compat.ml.executable_bindings import (
    ExecutableKind,
    import_local_executable,
)


def get_trainer(trainer_id: str) -> Trainer[object, object]:
    """Load and return a worker-local executable trainer."""

    import_local_executable(ExecutableKind.TRAINER, trainer_id)
    registered = get_registered_trainer(trainer_id)
    if registered is None:
        raise KeyError(
            f"trainer_id={trainer_id!r} was imported but did not register an executable"
        )
    return registered


__all__ = ["get_trainer", "trainer"]
