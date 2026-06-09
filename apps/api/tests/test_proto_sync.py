from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROTO_SOURCE = REPO_ROOT / "protos" / "sc" / "v1" / "sample.proto"
GENERATED_DIR = REPO_ROOT / "libs" / "protos" / "src" / "proto_stubs"


def test_proto_source_exists() -> None:
    assert PROTO_SOURCE.exists(), f"Proto source not found: {PROTO_SOURCE}"


def test_no_proto_copies_in_apps() -> None:
    result = subprocess.run(
        ["find", "apps/api", "apps/web", "-name", "sample.proto", "-not", "-path", "*/features/sc/proto/*"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    found = result.stdout.strip()
    assert found == "", f"Unexpected proto copies found:\n{found}"


def test_generated_stubs_exist() -> None:
    stub = GENERATED_DIR / "sc" / "v1" / "sample_pb2.py"
    assert stub.exists(), f"Generated stub not found: {stub}"


def test_generated_stubs_importable() -> None:
    import importlib.util

    stub_path = GENERATED_DIR / "sc" / "v1" / "sample_pb2.py"
    spec = importlib.util.spec_from_file_location("sample_pb2", stub_path)
    assert spec is not None, "Could not create module spec for sample_pb2.py"
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module is not None
