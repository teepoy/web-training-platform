from __future__ import annotations

from dataclasses import dataclass

from app.shared.context import SharedInfra


@dataclass
class AuthContext:
    pass


def init_auth(shared: SharedInfra) -> AuthContext:
    return AuthContext()
