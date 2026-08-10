from __future__ import annotations

import ast
from pathlib import Path

from ml_library import Prediction


def test_optional_library_models_are_plain_values() -> None:
    prediction = Prediction("sample-1", "", None, error="missing")

    assert prediction.error == "missing"


def test_optional_library_does_not_import_api_internals() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "ml_library"
    imported_modules: set[str] = set()
    for source_path in source_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        imported_modules.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )

    assert not any(
        module == "app" or module.startswith("app.") for module in imported_modules
    )
