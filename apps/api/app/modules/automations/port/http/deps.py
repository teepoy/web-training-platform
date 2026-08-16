from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.automations.port.local import AutomationOverviewPort
from app.shared.injection import resolve


def get_automation_overview(request: Request) -> AutomationOverviewPort:
    return resolve(request, AutomationOverviewPort)


AutomationOverviewDep = Annotated[
    AutomationOverviewPort, Depends(get_automation_overview)
]
