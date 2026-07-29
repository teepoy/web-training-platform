from __future__ import annotations

from dataclasses import dataclass

from injector import Module, inject, provider, singleton

from app.core.config import AppConfig
from app.modules.runtime.app.services.routing_service import ConfigRuntimeRoutingService
from app.modules.runtime.port.local import RuntimeRoutingPort
from app.shared.context import SharedInfra


@dataclass
class RuntimeContext:
    routing_service: ConfigRuntimeRoutingService


def init_runtime(shared: SharedInfra) -> RuntimeContext:
    return RuntimeContext(
        routing_service=ConfigRuntimeRoutingService(shared.config),
    )


class RuntimeModule(Module):
    @inject
    @provider
    @singleton
    def provide_runtime_context(self, config: AppConfig) -> RuntimeContext:
        return RuntimeContext(
            routing_service=ConfigRuntimeRoutingService(config),
        )

    @provider
    @singleton
    def provide_runtime_routing(self, context: RuntimeContext) -> RuntimeRoutingPort:
        return context.routing_service
