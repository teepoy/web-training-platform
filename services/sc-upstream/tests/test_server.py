from __future__ import annotations

import asyncio
from types import SimpleNamespace
import threading
from typing import Any, cast
from unittest.mock import AsyncMock

from pytest import MonkeyPatch, raises

from sc_upstream.server import (
    _load_adapter_factory,
    _shutdown_servers,
    _validate_adapter_contract,
)


class _BlockingFlightServer:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def shutdown(self) -> None:
        self.started.set()
        self.release.wait()


def test_shutdown_does_not_wait_for_blocking_flight_requests() -> None:
    grpc_server = AsyncMock()
    flight_server = _BlockingFlightServer()

    asyncio.run(_shutdown_servers(cast(Any, grpc_server), cast(Any, flight_server)))

    assert flight_server.started.wait(timeout=1)
    grpc_server.stop.assert_awaited_once_with(0)
    flight_server.release.set()


def test_adapter_factory_is_loaded_through_the_production_interface(
    monkeypatch: MonkeyPatch,
) -> None:
    upstream = object()
    zips = object()

    def factory() -> tuple[object, object]:
        return upstream, zips

    monkeypatch.setattr(
        "sc_upstream.server.importlib.import_module",
        lambda _module_name: SimpleNamespace(build=factory),
    )

    loaded = _load_adapter_factory("real_sc_adapter:build")

    assert loaded() == (upstream, zips)


def test_adapter_contract_requires_bounded_membership_reads() -> None:
    upstream = SimpleNamespace(
        get_inspection=lambda: None,
        list_inspections=lambda: None,
        list_discovery_inspections=lambda: None,
        list_samples=lambda: None,
        get_sample_count=lambda: None,
        open_list_samples_stream=lambda: None,
        list_review_images=lambda: None,
    )
    zips = SimpleNamespace(get_inspection_patch_zips=lambda: None)

    with raises(RuntimeError, match="open_membership_samples_stream"):
        _validate_adapter_contract(cast(Any, upstream), cast(Any, zips))
