from __future__ import annotations

from dataclasses import dataclass

from app.shared.context import SharedInfra


@dataclass
class ClassifyContext:
    """Classify module context.

    Lightweight container — classify creates SqlRepository and other
    dependencies on-the-fly in port/http/deps.py.
    """

    pass


def init_classify(shared: SharedInfra) -> ClassifyContext:
    """Build the classify module context from shared infrastructure.

    Args:
        shared: Shared infrastructure (session_factory, config, etc.).

    Returns:
        A new ClassifyContext instance.
    """
    return ClassifyContext()
