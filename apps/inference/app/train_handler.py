from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

from app.job_registry import JobRegistry
from app.metrics import TASK_KIND_TRAINING, jobs_active

logger = logging.getLogger(__name__)

# ── Per-job cancellation tracking ───────────────────────────────────
# Maps gpu_job_id → subprocess.Popen for active training subprocesses.
_active_subprocesses: dict[str, subprocess.Popen[bytes]] = {}


def _find_api_src_dir() -> str | None:
    """Locate the API source directory so we can run the training runner.

    Resolution order:
    1. ``API_SRC_DIR`` environment variable
    2. Repo-relative path (``apps/inference/`` → ``../../../apps/api/``)
    3. ``cwd/apps/api/`` (common Docker layout)
    """
    env_dir = os.environ.get("API_SRC_DIR")
    if env_dir and Path(env_dir).is_dir():
        return env_dir
    # From apps/inference/app/train_handler.py → ../../api/ (apps/api/)
    candidates: list[Path] = [
        Path(__file__).resolve().parents[2] / "api",
        Path.cwd() / "apps" / "api",
    ]
    for d in candidates:
        if (d / "app" / "runtime" / "training_runner.py").exists():
            return str(d)
    return None


def _build_training_command(
    api_src_dir: str,
    job_id: str,
    dataset_id: str,
    preset_id: str,
) -> list[str]:
    """Build the subprocess command to invoke the training runner.

    Uses ``uv run --package finetune-api`` when running inside a uv workspace,
    otherwise falls back to direct ``python -m`` with the API directory on
    ``PYTHONPATH``.
    """
    api_src = Path(api_src_dir)
    workspace_root = api_src.parent.parent
    workspace_toml = workspace_root / "pyproject.toml"

    if workspace_toml.exists() and shutil_which("uv"):
        return [
            "uv",
            "run",
            "--directory",
            str(workspace_root),
            "--package",
            "finetune-api",
            "--",
            sys.executable,
            "-m",
            "app.runtime.training_runner",
            "--job-id",
            job_id,
            "--dataset-id",
            dataset_id,
            "--preset-id",
            preset_id,
        ]

    return [
        sys.executable,
        "-m",
        "app.runtime.training_runner",
        "--job-id",
        job_id,
        "--dataset-id",
        dataset_id,
        "--preset-id",
        preset_id,
    ]


def _build_subprocess_env(api_src_dir: str) -> dict[str, str]:
    """Build environment dict for the training subprocess.

    Adds the API source parent (``apps/``) to ``PYTHONPATH`` so that
    ``import app`` resolves to the API's ``app/`` package, not the
    inference worker's ``app/``.
    """
    env = os.environ.copy()
    api_parent = str(Path(api_src_dir).parent)
    env["PYTHONPATH"] = api_parent + os.pathsep + env.get("PYTHONPATH", "")
    return env


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def _extract_error(stderr_text: str) -> str:
    """Extract a user-facing error message from stderr output.

    Special-cases GPU OOM and common runtime errors.
    """
    oom_markers = ["OutOfMemoryError", "out of memory", "CUDA out of memory"]
    for line in reversed(stderr_text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        for marker in oom_markers:
            if marker in stripped:
                return f"GPU out of memory: {stripped}"
        if "RuntimeError" in stripped or "Error:" in stripped:
            return stripped
    # Last non-empty line as fallback
    for line in reversed(stderr_text.splitlines()):
        if line.strip():
            return line.strip()
    return "Unknown training error"


def run_training_background(
    registry: JobRegistry,
    gpu_job_id: str,
    platform_job_id: str,
    dataset_id: str,
    preset_id: str,
) -> None:
    """Run the training pipeline in a background thread.

    This is the entry point called from the ``POST /v1/train`` route handler.
    It locates the API source directory, spawns a subprocess that calls
    ``run_training_pipeline()``, and updates the job registry on completion.

    Job state transitions:
    * ``pending`` → ``running`` → ``completed`` (success)
    * ``pending`` → ``running`` → ``failed``    (error / timeout / OOM)
    * ``pending`` → ``running`` → ``cancelled`` (cancel endpoint)
    """
    api_src_dir = _find_api_src_dir()

    if api_src_dir is None:
        _fail_job(
            registry,
            gpu_job_id,
            "API source directory not found — set API_SRC_DIR environment variable",
        )
        return

    cmd = _build_training_command(api_src_dir, gpu_job_id, dataset_id, preset_id)

    env = os.environ.copy()

    # For the non-uv fallback path, ensure the API app/ directory is
    # discoverable via PYTHONPATH.
    api_parent = str(Path(api_src_dir).parent)
    if api_parent not in env.get("PYTHONPATH", ""):
        env["PYTHONPATH"] = api_parent + os.pathsep + env.get("PYTHONPATH", "")

    registry.update_status(gpu_job_id, "running")
    registry.append_log(
        gpu_job_id,
        "INFO",
        f"Starting training: dataset={dataset_id} preset={preset_id} "
        f"(platform_job_id={platform_job_id})",
    )
    logger.info("Training subprocess command: %s", cmd)

    proc: subprocess.Popen[bytes] | None = None
    training_timeout = int(os.environ.get("TRAINING_TIMEOUT_SECONDS", "7200"))

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=api_src_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _active_subprocesses[gpu_job_id] = proc

        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=training_timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            _active_subprocesses.pop(gpu_job_id, None)
            registry.update_status(
                gpu_job_id,
                "failed",
                error=f"Training timed out after {training_timeout}s",
            )
            registry.append_log(
                gpu_job_id,
                "ERROR",
                f"Training timed out after {training_timeout}s",
            )
            jobs_active.labels(task_kind=TASK_KIND_TRAINING).set(0)
            return

        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        # Check if job was cancelled while running
        if registry.get(gpu_job_id) and registry.get(gpu_job_id).status == "cancelled":  # type: ignore[union-attr]
            registry.append_log(gpu_job_id, "INFO", "Training was cancelled")
            return

        if proc.returncode == 0:
            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            try:
                result = json.loads(stdout_text)
            except json.JSONDecodeError:
                # Non-JSON output — treat as success but log warning
                registry.update_status(gpu_job_id, "completed", progress=1.0)
                registry.append_log(
                    gpu_job_id,
                    "WARNING",
                    f"Training completed but stdout was not valid JSON: {stdout_text[:200]}",
                )
                jobs_active.labels(task_kind=TASK_KIND_TRAINING).set(0)
                return
            metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
            registry.update_status(
                gpu_job_id,
                "completed",
                metrics=metrics,
                progress=1.0,
            )
            registry.append_log(gpu_job_id, "INFO", "Training completed successfully")
            jobs_active.labels(task_kind=TASK_KIND_TRAINING).set(0)
            logger.info(
                "Training completed: gpu_job_id=%s result=%s", gpu_job_id, result
            )
        else:
            error_msg = _extract_error(stderr_text)
            registry.update_status(gpu_job_id, "failed", error=error_msg)
            registry.append_log(gpu_job_id, "ERROR", f"Training failed: {error_msg}")
            jobs_active.labels(task_kind=TASK_KIND_TRAINING).set(0)
            logger.error(
                "Training failed: gpu_job_id=%s returncode=%s stderr=%s",
                gpu_job_id,
                proc.returncode,
                stderr_text[:500],
            )

    except FileNotFoundError:
        _fail_job(
            registry,
            gpu_job_id,
            f"Training runner not found. Ensure the API package is installed "
            f"and API_SRC_DIR points to the correct directory. (tried: {api_src_dir})",
        )
    except Exception as exc:
        _fail_job(registry, gpu_job_id, f"Training execution error: {exc}")
        logger.exception("Training execution failed: gpu_job_id=%s", gpu_job_id)
    finally:
        _active_subprocesses.pop(gpu_job_id, None)


def cancel_training(gpu_job_id: str) -> bool:
    """Kill the subprocess for a running training job.

    Returns True if a subprocess was found and killed, False otherwise.
    """
    proc = _active_subprocesses.get(gpu_job_id)
    if proc is None:
        return False
    try:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return True
    except ProcessLookupError:
        return False


def _fail_job(registry: JobRegistry, gpu_job_id: str, error: str) -> None:
    """Mark a job as failed with an error message."""
    registry.update_status(gpu_job_id, "failed", error=error)
    registry.append_log(gpu_job_id, "ERROR", error)
    jobs_active.labels(task_kind=TASK_KIND_TRAINING).set(0)
    logger.error("Training job %s failed: %s", gpu_job_id, error)
