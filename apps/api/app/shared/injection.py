from __future__ import annotations

from typing import TypeVar, Type

from fastapi import Request
from injector import Injector


T = TypeVar("T")


def get_injector(request: Request) -> Injector:
    injector = getattr(request.app.state.app_context, "injector", None)
    if injector is None:
        raise RuntimeError("App injector has not been initialized")
    return injector


def resolve(request: Request, interface: Type[T]) -> T:
    return get_injector(request).get(interface)
