from __future__ import annotations

from dataclasses import dataclass

from app.modules.agent.app.services.session_store import SessionStore
from app.shared.context import SharedInfra


@dataclass
class AgentContext:
    session_store: SessionStore


def init_agent(shared: SharedInfra) -> AgentContext:
    return AgentContext(session_store=SessionStore())
