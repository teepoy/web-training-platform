from __future__ import annotations


class _ProvidersNamespace:
    class Object:
        def __init__(self, obj: object) -> None:
            self._obj = obj

        def __call__(self) -> object:
            return self._obj


providers = _ProvidersNamespace()
