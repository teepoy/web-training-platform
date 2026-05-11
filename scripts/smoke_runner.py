#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
# ]
# ///
"""Unified seed → smoke orchestrator for the platform.

Usage::

    python scripts/smoke_runner.py --all                     # seed all, run all smokes
    python scripts/smoke_runner.py --dataset imagen-mock     # seed mock → batch smoke
    python scripts/smoke_runner.py --skip-seed               # only run smokes
    python scripts/smoke_runner.py --skip-smoke              # only run seeds
    python scripts/smoke_runner.py --all --timeout 300       # custom timeout
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from smoke_common import wait_for_api_ready  # noqa: E402

API_URL = "http://localhost:8000"
SCRIPTS_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Dataset → seed command mapping
# ---------------------------------------------------------------------------
PYTHON = sys.executable


def _script_cmd(script: str, *extra_args: str) -> list[str]:
    return [PYTHON, str(SCRIPTS_DIR / script), *extra_args]


DATASET_CONFIGS: dict[str, dict] = {
    "imagen-mock": {
        "seed_cmd": _script_cmd("seed_imagenet_dev.py", "--no-promote", "--no-model"),
        "smokes": ["batch"],
    },
    "imagen-real": {
        "seed_cmd": _script_cmd("seed_imagenet_real.py", "--no-promote", "--no-model"),
        "smokes": ["batch"],
    },
    "oxford-flowers": {
        "seed_cmd": _script_cmd("seed.py", "oxford-flowers", "--no-promote"),
        "smokes": [],
    },
    "wafer-demo": {
        "seed_cmd": _script_cmd("seed.py", "wafer-demo", "--no-promote"),
        "smokes": [],
    },
    "multi-image-scatter": {
        "seed_cmd": _script_cmd("seed.py", "multi-image-scatter", "--no-promote"),
        "smokes": [],
    },
}

SMOKE_SCRIPTS: dict[str, list[str]] = {
    "batch": _script_cmd("smoke_dev_batch.py"),
    "training": _script_cmd("smoke_dev_training.py"),
    "prediction": _script_cmd("smoke_dev_prediction.py"),
}

ALL_DATASETS = list(DATASET_CONFIGS.keys())
ALL_SMOKES = list(SMOKE_SCRIPTS.keys())

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    label: str
    success: bool
    elapsed: float = 0.0
    exit_code: int = -1
    error: str = ""


@dataclass
class RunReport:
    results: list[StepResult] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def failures(self) -> list[StepResult]:
        return [r for r in self.results if not r.success]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def all_passed(self) -> bool:
        return self.passed == self.total


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def run_script(
    cmd: list[str],
    label: str,
    timeout: int | None = None,
) -> StepResult:
    """Run a single script via subprocess and return a StepResult."""
    print(f"\n{'─' * 60}")
    print(f"  ▶ {label}")
    print(f"  CMD: {' '.join(cmd)}")
    print(f"{'─' * 60}")

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=False,
            timeout=timeout,
            cwd=str(SCRIPTS_DIR.parent),
        )
        elapsed = time.time() - t0
        success = proc.returncode == 0
        if success:
            print(f"\n  ✓ {label} — PASS ({elapsed:.1f}s)")
        else:
            print(f"\n  ✗ {label} — FAIL (exit={proc.returncode}, {elapsed:.1f}s)")
        return StepResult(
            label=label,
            success=success,
            elapsed=elapsed,
            exit_code=proc.returncode,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.time() - t0
        msg = f"Timed out after {elapsed:.1f}s"
        print(f"\n  ✗ {label} — {msg}")
        return StepResult(
            label=label,
            success=False,
            elapsed=elapsed,
            exit_code=-1,
            error=str(exc),
        )
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"\n  ✗ {label} — ERROR: {exc}")
        return StepResult(
            label=label,
            success=False,
            elapsed=elapsed,
            exit_code=-1,
            error=str(exc),
        )


def print_summary(report: RunReport) -> None:
    """Print a summary table of all results."""
    total_elapsed = report.finished_at - report.started_at

    print(f"\n\n{'=' * 70}")
    print("  SMOKE RUNNER SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total steps:  {report.total}")
    print(f"  Passed:       {report.passed}")
    print(f"  Failed:       {len(report.failures)}")
    print(f"  Duration:     {total_elapsed:.1f}s")
    print(f"{'=' * 70}")

    if report.failures:
        print("\n  Failures:")
        for r in report.failures:
            extra = f" — {r.error}" if r.error else ""
            print(f"    ✗ {r.label} (exit={r.exit_code}, {r.elapsed:.1f}s){extra}")

    status = "ALL PASSED ✓" if report.all_passed else "SOME FAILED ✗"
    print(f"\n  {status}")
    print(f"{'=' * 70}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified seed → smoke orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available datasets: {", ".join(ALL_DATASETS)}
Available smokes:   {", ".join(ALL_SMOKES)}

Examples:
  python scripts/smoke_runner.py --all
  python scripts/smoke_runner.py --dataset imagen-mock
  python scripts/smoke_runner.py --skip-seed
  python scripts/smoke_runner.py --dataset imagen-mock --skip-smoke
""",
    )
    parser.add_argument(
        "--dataset",
        choices=ALL_DATASETS,
        help="Seed and smoke a specific dataset",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Seed all datasets then run all smoke scripts",
    )
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip seeding — only run smoke scripts (requires pre-seeded data)",
    )
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Alias for --skip-seed",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip smoke tests — only run seed scripts",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Timeout in seconds passed to each smoke script",
    )
    return parser


def resolve_plan(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    """Determine which datasets to seed and which smokes to run."""
    skip_seed = args.skip_seed or args.smoke_only
    skip_smoke = args.skip_smoke

    datasets: list[str]
    smokes: list[str]

    if args.all:
        datasets = [] if skip_seed else list(ALL_DATASETS)
        smokes = [] if skip_smoke else list(ALL_SMOKES)
    elif args.dataset:
        config = DATASET_CONFIGS[args.dataset]
        datasets = [] if skip_seed else [args.dataset]
        smokes = [] if skip_smoke else list(config["smokes"])
    elif skip_seed:
        # --skip-seed with no --all/--dataset: run all smokes on pre-seeded data
        datasets = []
        smokes = [] if skip_smoke else list(ALL_SMOKES)
    else:
        # No mode specified: error
        print("ERROR: specify --dataset, --all, --skip-seed, or --skip-smoke")
        print("       Use --help for full usage.")
        return [], []

    return datasets, smokes


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    datasets, smokes = resolve_plan(args)
    if not datasets and not smokes:
        return 1

    report = RunReport(started_at=time.time())

    print(f"\n{'#' * 70}")
    print("  SMOKE RUNNER")
    print(f"  Datasets to seed: {datasets if datasets else '(none)'}")
    print(f"  Smokes to run:    {smokes if smokes else '(none)'}")
    print(f"{'#' * 70}")

    # ── 1. Wait for API ──
    print(f"\n[0] Waiting for API health at {API_URL} ...")
    try:
        wait_for_api_ready(API_URL, timeout=120)
        print("  API is ready.")
    except RuntimeError as exc:
        print(f"  ERROR: {exc}")
        return 1

    # ── 2. Seed datasets ──
    for ds in datasets:
        config = DATASET_CONFIGS[ds]
        result = run_script(config["seed_cmd"], f"seed:{ds}")
        report.results.append(result)
        if not result.success:
            print(f"  ⚠ Seed '{ds}' failed — continuing with remaining steps.")

    # ── 3. Run smokes ──
    for sk in smokes:
        base_cmd = list(SMOKE_SCRIPTS[sk])
        if args.timeout is not None:
            base_cmd.extend(["--timeout", str(args.timeout)])
        result = run_script(base_cmd, f"smoke:{sk}")
        report.results.append(result)
        if not result.success:
            print(f"  ⚠ Smoke '{sk}' failed — continuing with remaining steps.")

    report.finished_at = time.time()
    print_summary(report)

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
