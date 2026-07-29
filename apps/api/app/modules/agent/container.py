from __future__ import annotations

from dataclasses import dataclass

from injector import Module, inject, provider, singleton

from app.modules.agent.app.services.session_store import SessionStore
from app.shared.context import SharedInfra


@dataclass
class AgentContext:
    session_store: SessionStore


def init_agent(shared: SharedInfra) -> AgentContext:
    return AgentContext(session_store=SessionStore())


class AgentModule(Module):
    @inject
    @provider
    @singleton
    def provide_agent_context(self) -> AgentContext:
        return AgentContext(session_store=SessionStore())

    @provider
    @singleton
    def provide_session_store(self, context: AgentContext) -> SessionStore:
        return context.session_store
