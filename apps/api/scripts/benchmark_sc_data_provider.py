"""Benchmark an HTTP SQL/Arrow SC data-provider endpoint.

Example:
    uv run python scripts/benchmark_sc_data_provider.py \
      --query-url http://localhost:8001/api/v1/sc/data/datasets/example/query \
      --events-url http://localhost:8001/api/v1/sc/data/datasets/example/events \
      --health-url http://localhost:8001/health \
      --sql 'SELECT defect_id, rough_bin FROM samples ORDER BY defect_id LIMIT ?' \
      --parameters-json '[300000]' \
      --description benchmark.sc-data-provider \
      --org-id default \
      --iterations 30 \
      --reconnect-cycles 100
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QuerySample:
    elapsed_ms: float
    response_bytes: int
    revision: int
    worker_pid: int
    cache_status: str
    spill_bytes: int
    server_timing: str


@dataclass(frozen=True)
class HealthSample:
    elapsed_ms: float
    payload: dict[str, Any]


def _headers(args: argparse.Namespace) -> dict[str, str]:
    result = {"Content-Type": "application/json"}
    if args.token:
        result["Authorization"] = f"Bearer {args.token}"
    if args.org_id:
        result["X-Organization-ID"] = args.org_id
    return result


def _query(args: argparse.Namespace) -> QuerySample:
    request = urllib.request.Request(
        args.query_url,
        data=json.dumps(
            {
                "description": args.description,
                "sql": args.sql,
                "parameters": json.loads(args.parameters_json),
            }
        ).encode(),
        headers=_headers(args),
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=args.timeout_seconds) as response:
        payload = response.read()
        elapsed_ms = (time.perf_counter() - started) * 1000
        return QuerySample(
            elapsed_ms=elapsed_ms,
            response_bytes=len(payload),
            revision=int(response.headers["X-SC-Data-Revision"]),
            worker_pid=int(response.headers["X-SC-Worker-PID"]),
            cache_status=response.headers["X-SC-Cache"],
            spill_bytes=int(response.headers.get("X-SC-Spill-Bytes", "0")),
            server_timing=response.headers.get("Server-Timing", ""),
        )


def _health(args: argparse.Namespace) -> HealthSample:
    request = urllib.request.Request(args.health_url, headers=_headers(args))
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=args.timeout_seconds) as response:
        payload = json.loads(response.read())
    return HealthSample(
        elapsed_ms=(time.perf_counter() - started) * 1000,
        payload=payload,
    )


def _reconnect_events(args: argparse.Namespace) -> None:
    if not args.events_url:
        return
    request = urllib.request.Request(args.events_url, headers=_headers(args))
    with urllib.request.urlopen(request, timeout=args.timeout_seconds) as response:
        for _line_number in range(4):
            if not response.readline():
                break


def _disconnect_query(args: argparse.Namespace) -> None:
    request = urllib.request.Request(
        args.query_url,
        data=json.dumps(
            {
                "description": args.description,
                "sql": args.sql,
                "parameters": json.loads(args.parameters_json),
            }
        ).encode(),
        headers=_headers(args),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout_seconds) as response:
            response.read(args.disconnect_after_bytes)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"disconnect probe returned HTTP {exc.code}: {detail}"
        ) from exc


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _cgroup_snapshot(cgroups: dict[str, Path]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, root in cgroups.items():
        events: dict[str, int] = {}
        try:
            for line in (
                (root / "memory.events").read_text(encoding="utf-8").splitlines()
            ):
                key, value = line.split(maxsplit=1)
                events[key] = int(value)
        except (OSError, ValueError):
            pass
        try:
            pids = sorted(
                int(value)
                for value in (root / "cgroup.procs").read_text(encoding="utf-8").split()
            )
        except (OSError, ValueError):
            pids = []
        result[name] = {
            "memory_current": _read_int(root / "memory.current"),
            "memory_peak": _read_int(root / "memory.peak"),
            "memory_events": events,
            "pids": pids,
        }
    return result


def _parse_cgroups(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path:
            raise ValueError(f"invalid cgroup mapping {value!r}; expected NAME=PATH")
        result[name] = Path(raw_path)
    return result


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile))
    return ordered[index]


def _summary(samples: list[QuerySample]) -> dict[str, Any]:
    elapsed = [sample.elapsed_ms for sample in samples]
    return {
        "count": len(samples),
        "p50_ms": statistics.median(elapsed),
        "p95_ms": _percentile(elapsed, 0.95),
        "response_bytes": sorted({sample.response_bytes for sample in samples}),
        "worker_pids": sorted({sample.worker_pid for sample in samples}),
        "cache_statuses": sorted({sample.cache_status for sample in samples}),
        "revisions": sorted({sample.revision for sample in samples}),
        "max_spill_bytes_at_headers": max(sample.spill_bytes for sample in samples),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-url", required=True)
    parser.add_argument("--events-url")
    parser.add_argument("--health-url", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--sql", required=True)
    parser.add_argument("--parameters-json", default="[]")
    parser.add_argument("--token")
    parser.add_argument("--org-id")
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--reconnect-cycles", type=int, default=100)
    parser.add_argument("--disconnect-cycles", type=int, default=1)
    parser.add_argument("--disconnect-after-bytes", type=int, default=1)
    parser.add_argument(
        "--cgroup",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="sample cgroup v2 memory.current/peak/events and cgroup.procs",
    )
    parser.add_argument("--timeout-seconds", type=float, default=40)
    args = parser.parse_args()
    if args.iterations < 2:
        parser.error("--iterations must be at least 2")
    if args.reconnect_cycles < 0:
        parser.error("--reconnect-cycles must not be negative")
    if args.disconnect_cycles < 0 or args.disconnect_after_bytes <= 0:
        parser.error("disconnect cycles must be non-negative and bytes positive")
    try:
        cgroups = _parse_cgroups(args.cgroup)
    except ValueError as exc:
        parser.error(str(exc))

    cgroup_before = _cgroup_snapshot(cgroups)
    cold = _query(args)
    warm = [_query(args) for _index in range(args.iterations)]
    health_before = _health(args)
    reconnect_samples: list[QuerySample] = []
    health_samples: list[HealthSample] = []
    cgroup_samples: list[dict[str, Any]] = []
    for _index in range(args.reconnect_cycles):
        _reconnect_events(args)
        reconnect_samples.append(_query(args))
        health_samples.append(_health(args))
        if cgroups:
            cgroup_samples.append(_cgroup_snapshot(cgroups))
    for _index in range(args.disconnect_cycles):
        _disconnect_query(args)
        health_samples.append(_health(args))
    health_after = _health(args)
    cgroup_after = _cgroup_snapshot(cgroups)

    rss_samples = [float(item.payload["rss_mb"]) for item in health_samples]
    temp_samples = [int(item.payload["duckdb_temp_bytes"]) for item in health_samples]
    health_latencies = [item.elapsed_ms for item in health_samples]
    report = {
        "cold": asdict(cold),
        "warm": _summary(warm),
        "reconnect": _summary(reconnect_samples) if reconnect_samples else None,
        "health_before": asdict(health_before),
        "health_after": asdict(health_after),
        "health_latency": {
            "p50_ms": statistics.median(health_latencies) if health_latencies else None,
            "p95_ms": _percentile(health_latencies, 0.95) if health_latencies else None,
        },
        "refresh_memory": {
            "rss_first_mb": rss_samples[0] if rss_samples else None,
            "rss_last_mb": rss_samples[-1] if rss_samples else None,
            "rss_max_mb": max(rss_samples) if rss_samples else None,
            "duckdb_temp_max_bytes": max(temp_samples) if temp_samples else None,
        },
        "client_disconnect_cycles": args.disconnect_cycles,
        "cgroup_before": cgroup_before,
        "cgroup_after": cgroup_after,
        "cgroup_samples": cgroup_samples,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
