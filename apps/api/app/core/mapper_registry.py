from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class MapperRegistry:
    """Global mapper registry.

    Maps ``(src_key, dst_key)`` pairs to conversion functions.
    Both types and string names are supported as keys via
    :meth:`register` which accepts lists of identifiers and
    registers the cartesian product.
    """

    def __init__(self) -> None:
        self._mappers: dict[tuple[str, str], Callable[..., Any]] = {}

    @staticmethod
    def _resolve_key(type_or_name: type | str) -> str:
        if isinstance(type_or_name, str):
            return type_or_name
        module = getattr(type_or_name, "__module__", None)
        qualname = getattr(type_or_name, "__qualname__", None)
        if module and qualname:
            return f"{module}.{qualname}"
        return repr(type_or_name)

    def register(
        self,
        from_types: Sequence[type | str],
        to_types: Sequence[type | str],
    ) -> Callable[[F], F]:
        """Decorator: register a mapper function for all ``from × to`` combinations.

        Each element may be a Python type (class) or a string identifier
        (e.g. ``"image_sc"``, ``"patch_image_v1"``).

        Raises:
            ValueError: if any combination is already registered.
        """
        from_keys = [self._resolve_key(t) for t in from_types]
        to_keys = [self._resolve_key(t) for t in to_types]

        def decorator(func: F) -> F:
            for src in from_keys:
                for dst in to_keys:
                    key = (src, dst)
                    if key in self._mappers:
                        raise ValueError(
                            f"Duplicate mapper registration: {src} -> {dst}"
                        )
                    self._mappers[key] = func
            return func

        return decorator

    def get_mapper(
        self,
        src_type: type | str,
        dst_type: type | str,
    ) -> Callable[..., Any]:
        """Look up a mapper by source and destination identifiers.

        Raises:
            KeyError: if no mapper is registered for the pair.
        """
        src_key = self._resolve_key(src_type)
        dst_key = self._resolve_key(dst_type)
        key = (src_key, dst_key)
        if key not in self._mappers:
            raise KeyError(f"No mapper registered for {src_key} -> {dst_key}")
        return self._mappers[key]


mapper = MapperRegistry()
