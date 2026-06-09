from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
OPENAPI_SPEC = REPO_ROOT / "openapi" / "openapi.yaml"


def test_openapi_spec_exists() -> None:
    assert OPENAPI_SPEC.exists(), f"OpenAPI spec not found: {OPENAPI_SPEC}"


def test_no_duplicate_operation_ids() -> None:
    doc = yaml.safe_load(OPENAPI_SPEC.read_text(encoding="utf-8"))
    paths = doc.get("paths", {})
    seen: list[str] = []
    duplicates: list[str] = []
    for _path, methods in paths.items():
        for _method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            op_id = operation.get("operationId")
            if op_id is None:
                continue
            if op_id in seen:
                duplicates.append(op_id)
            else:
                seen.append(op_id)
    assert not duplicates, f"Duplicate operationIds: {duplicates}"


@pytest.mark.slow
def test_openapi_sync() -> None:
    result = subprocess.run(
        ["make", "check-openapi-sync"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"make check-openapi-sync failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
