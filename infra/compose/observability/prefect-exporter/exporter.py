"""
Prefect aggregate metrics exporter for Prometheus scraping.

Replaces: prometheus-prefect-exporter community image.
Usage: mounted into the prefect-exporter Compose service.

Metrics exposed:
  prefect_health                       gauge
  prefect_flow_runs_total              gauge  by state, scrape window
  prefect_work_queue_depth             gauge  by work_queue_name
  prefect_flow_run_duration_seconds    histogram  completed runs in scrape window
  prefect_flow_run_queue_time_seconds  histogram  created to start time in scrape window

Env vars:
  PREFECT_API_URL         (default http://prefect-server:4200/api)
  EXPORTER_PORT           (default 8000)
  SCRAPE_WINDOW_MINUTES   (default 30)
  QUEUE_WINDOW_MINUTES    (default 60)
"""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen

PREFECT_URL: str = os.getenv("PREFECT_API_URL", "http://prefect-server:4200/api")
SCRAPE_WINDOW: int = int(os.getenv("SCRAPE_WINDOW_MINUTES", "30"))
QUEUE_WINDOW: int = int(os.getenv("QUEUE_WINDOW_MINUTES", "60"))

DURATION_BUCKETS: list[float] = [30, 60, 300, 900, 1800, 3600, 7200, 14400]

ALL_STATES: list[str] = [
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "RUNNING",
    "SCHEDULED",
    "PENDING",
    "CRASHED",
    "CANCELLING",
]


def _post(path: str, body: dict) -> list | dict:
    url = f"{PREFECT_URL}{path}"
    data = json.dumps(body).encode()
    req = Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _iso_minutes_ago(minutes: int) -> str:
    t = time.gmtime(time.time() - minutes * 60)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", t)


def _fetch_health() -> int:
    try:
        with urlopen(f"{PREFECT_URL}/health", timeout=5) as resp:
            data = json.loads(resp.read())
        return 1 if (data is True or data) else 0
    except Exception:
        return 0


def _fetch_flow_run_counts() -> dict[str, int]:
    counts: dict[str, int] = {s: 0 for s in ALL_STATES}
    since = _iso_minutes_ago(SCRAPE_WINDOW)
    for state in ALL_STATES:
        try:
            body = {
                "flow_runs": {
                    "operator": "and_",
                    "state": {"operator": "and_", "type": {"any_": [state]}},
                    "start_time": {"after_": since},
                },
                "limit": 200,
            }
            result = _post("/flow_runs/filter", body)
            counts[state] = len(result) if isinstance(result, list) else 0
        except Exception:
            pass
    return counts


def _fetch_work_queue_depths() -> list[tuple[str, int]]:
    depths: list[tuple[str, int]] = []
    try:
        queues = _post("/work_queues/filter", {"limit": 100})
        if not isinstance(queues, list):
            return depths
        for q in queues:
            name = q.get("name", "unknown")
            # Count SCHEDULED flow runs per named work queue as queue depth proxy.
            since = _iso_minutes_ago(QUEUE_WINDOW)
            try:
                body = {
                    "flow_runs": {
                        "operator": "and_",
                        "state": {"operator": "and_", "type": {"any_": ["SCHEDULED"]}},
                        "work_queue_name": {"any_": [name]},
                        "expected_start_time": {"after_": since},
                    },
                    "limit": 500,
                }
                result = _post("/flow_runs/filter", body)
                depth = len(result) if isinstance(result, list) else 0
            except Exception:
                depth = 0
            depths.append((name, depth))
    except Exception:
        pass
    return depths


def _fetch_completed_runs() -> list[dict]:
    since = _iso_minutes_ago(SCRAPE_WINDOW)
    runs: list[dict] = []
    for state in ("COMPLETED", "FAILED"):
        try:
            body = {
                "flow_runs": {
                    "operator": "and_",
                    "state": {"operator": "and_", "type": {"any_": [state]}},
                    "start_time": {"after_": since},
                },
                "limit": 200,
            }
            result = _post("/flow_runs/filter", body)
            if isinstance(result, list):
                runs.extend(result)
        except Exception:
            pass
    return runs


def _histogram_lines(metric: str, help_text: str, samples: list[float]) -> list[bytes]:
    lines: list[bytes] = [
        f"# HELP {metric} {help_text}".encode(),
        f"# TYPE {metric} histogram".encode(),
    ]
    counts = {b: 0 for b in DURATION_BUCKETS}
    for v in samples:
        for b in DURATION_BUCKETS:
            if v <= b:
                counts[b] += 1
    cumulative = 0
    for b in DURATION_BUCKETS:
        cumulative += counts[b]
        lines.append(f'{metric}_bucket{{le="{b}"}} {cumulative}'.encode())
    lines.append(f'{metric}_bucket{{le="+Inf"}} {len(samples)}'.encode())
    lines.append(f"{metric}_sum {sum(samples):.3f}".encode())
    lines.append(f"{metric}_count {len(samples)}".encode())
    return lines


def _parse_iso(ts: str | None) -> float | None:
    if not ts:
        return None
    # Strip sub-seconds and timezone suffix so strptime handles bare %Y-%m-%dT%H:%M:%S.
    ts = ts.rstrip("Z").split("+")[0].split(".")[0]
    try:
        return float(time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%S")))
    except Exception:
        return None


def collect_metrics() -> list[bytes]:
    lines: list[bytes] = []

    healthy = _fetch_health()
    lines += [
        b"# HELP prefect_health Prefect server health status (1=healthy, 0=unreachable)",
        b"# TYPE prefect_health gauge",
        f"prefect_health {healthy}".encode(),
    ]

    if not healthy:
        return lines

    counts = _fetch_flow_run_counts()
    lines += [
        b"# HELP prefect_flow_runs_total Flow run counts by state in the scrape window",
        b"# TYPE prefect_flow_runs_total gauge",
    ]
    for state, count in counts.items():
        lines.append(
            f'prefect_flow_runs_total{{state="{state.lower()}"}} {count}'.encode()
        )

    depths = _fetch_work_queue_depths()
    lines += [
        b"# HELP prefect_work_queue_depth Scheduled flow run count per work queue",
        b"# TYPE prefect_work_queue_depth gauge",
    ]
    for name, depth in depths:
        lines.append(
            f'prefect_work_queue_depth{{work_queue_name="{name}"}} {depth}'.encode()
        )

    runs = _fetch_completed_runs()
    durations: list[float] = []
    queue_times: list[float] = []
    for run in runs:
        elapsed = run.get("elapsed_time")
        if elapsed is not None:
            try:
                durations.append(float(elapsed))
            except (TypeError, ValueError):
                pass
        created_ts = _parse_iso(run.get("created") or run.get("expected_start_time"))
        start_ts = _parse_iso(run.get("start_time"))
        if created_ts is not None and start_ts is not None and start_ts >= created_ts:
            queue_times.append(start_ts - created_ts)

    lines += _histogram_lines(
        "prefect_flow_run_duration_seconds",
        "Elapsed time of completed/failed flow runs in the scrape window (seconds)",
        durations,
    )
    lines += _histogram_lines(
        "prefect_flow_run_queue_time_seconds",
        "Time from flow run creation to start (seconds) in the scrape window",
        queue_times,
    )

    return lines


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            for line in collect_metrics():
                self.wfile.write(line + b"\n")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args, **kwargs) -> None:  # type: ignore[override]
        pass  # suppress HTTP request logging


def main() -> None:
    port = int(os.getenv("EXPORTER_PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    print(f"Prefect exporter listening on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
