from __future__ import annotations

import argparse
import os
import signal
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


@dataclass(frozen=True)
class HealthcheckConfig:
    urls: tuple[str, ...]
    timeout_seconds: float
    failure_threshold: int
    startup_grace_seconds: float
    state_file: Path
    force_container_restart: bool
    restart_target_pid_file: Path = Path("/tmp/perspective-ws-service.pid")
    restart_pid: int = 1


Probe = Callable[[Sequence[str], float], None]
ProcessAge = Callable[[int], float]
Restart = Callable[[Path], None]
Log = Callable[[str], None]


def probe_urls(urls: Sequence[str], timeout_seconds: float) -> None:
    def probe(url: str) -> None:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            if response.status >= 400:
                raise RuntimeError(f"{url} returned HTTP {response.status}")

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=len(urls)) as executor:
        results = [(url, executor.submit(probe, url)) for url in urls]
        for url, result in results:
            try:
                result.result()
            except Exception as exc:
                failures.append(f"{url}: {exc}")
    if failures:
        raise RuntimeError("; ".join(failures))


def process_age_seconds(pid: int) -> float:
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    fields_after_command = stat[stat.rfind(")") + 2 :].split()
    start_ticks = int(fields_after_command[19])
    ticks_per_second = os.sysconf("SC_CLK_TCK")
    system_uptime = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    return max(0.0, system_uptime - start_ticks / ticks_per_second)


def force_restart_container(pid_file: Path) -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("refusing to force restart outside a Docker container")
    pid = int(pid_file.read_text(encoding="utf-8").strip())
    if pid <= 1:
        raise RuntimeError(f"refusing to kill invalid service process group {pid}")
    os.killpg(pid, signal.SIGKILL)


def container_log(message: str) -> None:
    line = f"[perspective-healthcheck] {message}"
    print(line, file=sys.stderr, flush=True)
    try:
        with Path("/proc/1/fd/2").open("a", encoding="utf-8") as container_stderr:
            print(line, file=container_stderr, flush=True)
    except OSError:
        pass


def _failure_count(path: Path) -> int:
    try:
        return max(0, int(path.read_text(encoding="utf-8").strip()))
    except (FileNotFoundError, ValueError):
        return 0


def _write_failure_count(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(count), encoding="utf-8")


def _reset_failure_count(path: Path) -> None:
    path.unlink(missing_ok=True)


def run_healthcheck(
    config: HealthcheckConfig,
    *,
    probe: Probe = probe_urls,
    process_age: ProcessAge = process_age_seconds,
    restart: Restart = force_restart_container,
    log: Log = container_log,
) -> int:
    try:
        probe(config.urls, config.timeout_seconds)
    except Exception as exc:
        if not config.force_container_restart:
            log(f"probe failed: {exc}")
            return 1

        age_seconds = process_age(config.restart_pid)
        if age_seconds < config.startup_grace_seconds:
            _reset_failure_count(config.state_file)
            log(
                "probe failed during startup grace "
                f"({age_seconds:.1f}s/{config.startup_grace_seconds:.1f}s): {exc}"
            )
            return 1

        failures = _failure_count(config.state_file) + 1
        _write_failure_count(config.state_file, failures)
        log(f"probe failed ({failures}/{config.failure_threshold}): {exc}")
        if failures >= config.failure_threshold:
            log(
                "failure threshold reached; force restarting container through "
                f"service PID file {config.restart_target_pid_file}"
            )
            restart(config.restart_target_pid_file)
        return 1

    _reset_failure_count(config.state_file)
    return 0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> HealthcheckConfig:
    parser = argparse.ArgumentParser(
        description="Probe Perspective workers and restart unhealthy Docker containers"
    )
    parser.add_argument("--url", action="append", required=True, dest="urls")
    parser.add_argument("--timeout-seconds", type=float, default=2.0)
    parser.add_argument("--failure-threshold", type=_positive_int, default=3)
    parser.add_argument(
        "--startup-grace-seconds", type=_non_negative_float, default=60.0
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("/tmp/perspective-ws-healthcheck-failures"),
    )
    parser.add_argument(
        "--restart-target-pid-file",
        type=Path,
        default=Path("/tmp/perspective-ws-service.pid"),
    )
    parser.add_argument("--force-container-restart", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be greater than zero")
    return HealthcheckConfig(
        urls=tuple(args.urls),
        timeout_seconds=args.timeout_seconds,
        failure_threshold=args.failure_threshold,
        startup_grace_seconds=args.startup_grace_seconds,
        state_file=args.state_file,
        force_container_restart=args.force_container_restart,
        restart_target_pid_file=args.restart_target_pid_file,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_healthcheck(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
