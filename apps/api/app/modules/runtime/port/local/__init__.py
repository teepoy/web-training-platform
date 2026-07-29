from __future__ import annotations

from typing import Protocol

from app.modules.runtime.domain.routing import RuntimeDeploymentRoute


class RuntimeRoutingPort(Protocol):
    def training_route(self, trainer_id: str) -> RuntimeDeploymentRoute: ...

    def prediction_route(
        self,
        predictor_id: str,
    ) -> RuntimeDeploymentRoute: ...

    def train_and_predict_route(
        self,
        trainer_id: str,
    ) -> RuntimeDeploymentRoute: ...

    def materialization_route(
        self,
        materializer_id: str,
    ) -> RuntimeDeploymentRoute: ...


__all__ = ["RuntimeRoutingPort"]
