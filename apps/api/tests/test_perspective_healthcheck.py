from __future__ import annotations

import sys
from pathlib import Path

from scripts.perspective_container_watchdog import (
    parse_args as parse_watchdog_args,
)
from scripts.perspective_container_watchdog import (
    run_service,
)
from scripts.perspective_healthcheck import HealthcheckConfig, run_healthcheck


def config(tmp_path: Path, *, force_restart: bool = True) -> HealthcheckConfig:
    return HealthcheckConfig(
        urls=("http://localhost:8001/ready",),
        timeout_seconds=2,
        failure_threshold=3,
        startup_grace_seconds=60,
        state_file=tmp_path / "failures",
        force_container_restart=force_restart,
    )


def failing_probe(_urls: object, _timeout_seconds: float) -> None:
    raise RuntimeError("unavailable")


def test_success_resets_failure_count(tmp_path: Path) -> None:
    healthcheck = config(tmp_path)
    healthcheck.state_file.write_text("2", encoding="utf-8")

    result = run_healthcheck(healthcheck, probe=lambda _urls, _timeout: None)

    assert result == 0
    assert not healthcheck.state_file.exists()


def test_failure_below_threshold_does_not_restart(tmp_path: Path) -> None:
    restarted: list[Path] = []
    healthcheck = config(tmp_path)

    result = run_healthcheck(
        healthcheck,
        probe=failing_probe,
        process_age=lambda _pid: 120,
        restart=restarted.append,
        log=lambda _message: None,
    )

    assert result == 1
    assert healthcheck.state_file.read_text(encoding="utf-8") == "1"
    assert restarted == []


def test_failure_threshold_forces_restart(tmp_path: Path) -> None:
    restarted: list[Path] = []
    healthcheck = config(tmp_path)
    healthcheck.state_file.write_text("2", encoding="utf-8")

    result = run_healthcheck(
        healthcheck,
        probe=failing_probe,
        process_age=lambda _pid: 120,
        restart=restarted.append,
        log=lambda _message: None,
    )

    assert result == 1
    assert restarted == [healthcheck.restart_target_pid_file]


def test_startup_grace_resets_failures_without_restarting(tmp_path: Path) -> None:
    restarted: list[Path] = []
    healthcheck = config(tmp_path)
    healthcheck.state_file.write_text("2", encoding="utf-8")

    result = run_healthcheck(
        healthcheck,
        probe=failing_probe,
        process_age=lambda _pid: 10,
        restart=restarted.append,
        log=lambda _message: None,
    )

    assert result == 1
    assert not healthcheck.state_file.exists()
    assert restarted == []


def test_probe_only_never_restarts(tmp_path: Path) -> None:
    restarted: list[Path] = []

    result = run_healthcheck(
        config(tmp_path, force_restart=False),
        probe=failing_probe,
        process_age=lambda _pid: 120,
        restart=restarted.append,
        log=lambda _message: None,
    )

    assert result == 1
    assert restarted == []


def test_watchdog_parser_preserves_service_command(tmp_path: Path) -> None:
    pid_file = tmp_path / "service.pid"

    parsed_pid_file, command = parse_watchdog_args(
        ["--pid-file", str(pid_file), "--", "python", "-m", "app.perspective_main"]
    )

    assert parsed_pid_file == pid_file
    assert command == ("python", "-m", "app.perspective_main")


def test_watchdog_exits_nonzero_when_service_is_force_killed(tmp_path: Path) -> None:
    pid_file = tmp_path / "service.pid"

    result = run_service(
        (
            sys.executable,
            "-c",
            "import os, signal; os.kill(os.getpid(), signal.SIGKILL)",
        ),
        pid_file,
    )

    assert result == 137
    assert not pid_file.exists()
