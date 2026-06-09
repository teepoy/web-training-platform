from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _relative(path: Path) -> str:
    return path.relative_to(APP_ROOT).as_posix()


def test_no_dependency_injector_imports() -> None:
    ALLOWLIST: list[str] = []

    violations: list[str] = []
    for path in _python_files(APP_ROOT):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "dependency_injector" or alias.name.startswith("dependency_injector."):
                        violations.append(_relative(path))
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module == "dependency_injector" or node.module.startswith("dependency_injector."):
                    violations.append(_relative(path))

    unexpected = sorted(set(violations) - set(ALLOWLIST))
    assert unexpected == []


def test_no_state_container_in_http_deps() -> None:
    ALLOWLIST: list[str] = []

    http_roots = sorted(APP_ROOT.glob("modules/**/port/http"))
    violations = [
        _relative(path)
        for root in http_roots
        for path in _python_files(root)
        if ".state.container" in path.read_text()
    ]

    unexpected = sorted(set(violations) - set(ALLOWLIST))
    assert unexpected == []


def test_no_app_container_ref_in_production() -> None:
    ALLOWLIST: list[str] = []

    modules_root = APP_ROOT / "modules"
    violations = [
        path.name
        for path in _python_files(modules_root)
        if "tests" not in path.relative_to(modules_root).parts and "_app_container_ref" in path.read_text()
    ]

    unexpected = sorted(set(violations) - set(ALLOWLIST))
    assert unexpected == []


def test_no_shared_infra_module_repos() -> None:
    ALLOWLIST: list[str] = []

    context_path = APP_ROOT / "shared" / "context.py"
    tree = ast.parse(context_path.read_text(), filename=str(context_path))
    shared_infra = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SharedInfra"
    )
    forbidden_suffixes = ("_repository", "_service", "_orchestrator")
    violations = [
        node.target.id
        for node in shared_infra.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id.endswith(forbidden_suffixes)
    ]

    unexpected = sorted(set(violations) - set(ALLOWLIST))
    assert unexpected == []


def test_no_app_container_imports_outside_composition() -> None:
    ALLOWLIST: list[str] = [
        "modules/training/flows/train_job.py",
        "modules/prediction/flows/predict_job.py",
    ]

    excluded = {"composition.py", "main.py"}
    violations: list[str] = []
    for path in _python_files(APP_ROOT):
        if path.name in excluded:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_names = {alias.name for alias in node.names}
                if node.module == "app.composition" and "AppContainer" in imported_names:
                    violations.append(_relative(path))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "AppContainer" or alias.name.endswith(".AppContainer"):
                        violations.append(_relative(path))

    unexpected = sorted(set(violations) - set(ALLOWLIST))
    assert unexpected == []
