from __future__ import annotations

from typing import Any, Callable

from seedmaker.runner import SeedConfig, SeedRunner

_registry: dict[str, tuple[SeedConfig, Callable[[Any, SeedRunner], int]]] = {}


def register(config: SeedConfig, run_fn: Callable[[Any, SeedRunner], int]) -> None:
    _registry[config.name] = (config, run_fn)


def list_datasets() -> list[tuple[str, str, str]]:
    return [
        (name, cfg.dataset_name, cfg.description)
        for name, (cfg, _) in _registry.items()
    ]


def get(config_name: str) -> tuple[SeedConfig, Callable[[Any, SeedRunner], int]] | None:
    return _registry.get(config_name)
