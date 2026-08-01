from __future__ import annotations

import ast
import subprocess
import sys
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


def test_http_deps_use_injector_instead_of_app_context() -> None:
    ALLOWLIST: list[str] = []

    roots = sorted(APP_ROOT.glob("modules/**/port/http")) + [
        APP_ROOT / "modules" / "datasets" / "views"
    ]
    violations = [
        _relative(path)
        for root in roots
        for path in _python_files(root)
        if "request.app.state.app_context" in path.read_text()
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


def test_no_legacy_container_symbols() -> None:
    forbidden_names = {
        "AppContainer",
        "build_flow_container",
        "_with_app_container",
        "_run_prediction_job_with_container",
    }
    violations: list[str] = []
    for path in _python_files(APP_ROOT):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_names = {alias.name for alias in node.names}
                if imported_names & forbidden_names:
                    violations.append(_relative(path))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.rsplit(".", 1)[-1] in forbidden_names:
                        violations.append(_relative(path))
            elif isinstance(node, ast.Name) and node.id in forbidden_names:
                if not (
                    isinstance(node.ctx, ast.Load)
                    and node.id in {"AppContainer", "build_flow_container"}
                    and path.name == "test_architecture_boundaries.py"
                ):
                    violations.append(_relative(path))

    assert sorted(set(violations)) == []


def test_app_container_and_legacy_flow_container_are_removed() -> None:
    composition_path = APP_ROOT / "composition.py"
    tree = ast.parse(composition_path.read_text(), filename=str(composition_path))
    forbidden_defs = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name in {"AppContainer", "build_flow_container"}
    }

    assert forbidden_defs == set()


def test_production_code_does_not_read_sibling_app_contexts() -> None:
    forbidden_modules = {"datasets", "prediction", "training"}
    violations: list[str] = []

    for path in _python_files(APP_ROOT):
        if "tests" in path.parts:
            continue
        if path == APP_ROOT / "composition.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in forbidden_modules
                and isinstance(node.value, ast.Name)
                and node.value.id in {"app_context", "ctx"}
            ):
                violations.append(_relative(path))

    assert sorted(set(violations)) == []


def test_agent_does_not_import_sibling_service_implementations() -> None:
    agent_root = APP_ROOT / "modules" / "agent"
    violations: list[str] = []

    for path in _python_files(agent_root):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("app.modules.")
                and ".app.services." in node.module
                and not node.module.startswith("app.modules.agent.")
            ):
                violations.append(_relative(path))

    assert sorted(set(violations)) == []


def test_prediction_does_not_import_dataset_service_implementations() -> None:
    prediction_root = APP_ROOT / "modules" / "prediction"
    violations: list[str] = []

    for path in _python_files(prediction_root):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("app.modules.datasets.app.services")
            ):
                violations.append(_relative(path))

    assert sorted(set(violations)) == []


def test_production_code_imports_storage_from_storage_module() -> None:
    forbidden_modules = {
        "app.modules.datasets.adapter.db_full_storage",
        "app.modules.datasets.adapter.sparse_storage",
        "app.modules.datasets.adapter.storage_factory",
        "app.modules.datasets.app.services.sparse_import_operator",
        "app.modules.datasets.domain.storage_agg",
    }
    compatibility_shims = {
        "modules/datasets/adapter/db_full_storage.py",
        "modules/datasets/adapter/sparse_storage.py",
        "modules/datasets/adapter/storage_factory.py",
        "modules/datasets/app/services/sparse_import_operator.py",
        "modules/datasets/domain/storage_agg.py",
    }
    violations: list[str] = []

    for path in _python_files(APP_ROOT):
        rel = _relative(path)
        if "tests" in path.parts or rel in compatibility_shims:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in forbidden_modules:
                violations.append(rel)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_modules:
                        violations.append(rel)

    assert sorted(set(violations)) == []


def test_legacy_storage_compatibility_shims_are_removed() -> None:
    removed_paths = {
        "modules/datasets/adapter/db_full_storage.py",
        "modules/datasets/adapter/sparse_storage.py",
        "modules/datasets/adapter/storage_factory.py",
        "modules/datasets/app/services/dataset_payload_store.py",
        "modules/datasets/app/services/sparse_import_operator.py",
        "modules/datasets/app/services/sparse_manifest.py",
        "modules/datasets/domain/storage_agg.py",
        "modules/sc/app/services/inspection_materializer.py",
    }

    existing = [rel for rel in removed_paths if (APP_ROOT / rel).exists()]

    assert sorted(existing) == []


def test_production_code_does_not_read_storage_from_datasets_context() -> None:
    forbidden_attrs = {
        "dataset_payload_store",
        "dataset_storage_factory",
        "sparse_import_factory",
    }
    violations: list[str] = []

    for path in _python_files(APP_ROOT):
        rel = _relative(path)
        if "tests" in path.parts or path == APP_ROOT / "composition.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in forbidden_attrs
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "datasets"
            ):
                violations.append(rel)

    assert sorted(set(violations)) == []


def test_data_plane_contract_does_not_depend_on_api_storage_or_orm() -> None:
    data_plane_root = APP_ROOT / "modules" / "storage" / "domain" / "data_plane"
    forbidden_modules = (
        "app.modules.storage.adapter",
        "app.modules.storage.container",
        "app.modules.storage.port",
        "app.shared.db.",
        "app.modules.datasets.app.services",
        "app.modules.prediction.app.services",
        "app.modules.training.app.services",
        "app.modules.sc.app.services",
    )
    violations: list[str] = []

    for path in _python_files(data_plane_root):
        if "tests" in path.parts:
            continue
        rel = _relative(path)
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module.startswith(forbidden_modules):
                    violations.append(rel)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_modules):
                        violations.append(rel)

    assert sorted(set(violations)) == []


def test_production_code_imports_materializers_from_materializer_module() -> None:
    forbidden_module = "app.modules.sc.app.services.inspection_materializer"
    compatibility_shim = "modules/sc/app/services/inspection_materializer.py"
    violations: list[str] = []

    for path in _python_files(APP_ROOT):
        rel = _relative(path)
        if "tests" in path.parts or rel == compatibility_shim:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == forbidden_module:
                violations.append(rel)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == forbidden_module:
                        violations.append(rel)

    assert sorted(set(violations)) == []


def test_api_runtime_contracts_do_not_import_web_or_db_infra() -> None:
    repo_root = APP_ROOT.parents[2]
    roots = [
        APP_ROOT / "shared" / "domain" / "runtime.py",
        APP_ROOT / "shared" / "domain" / "data_plane.py",
    ]
    forbidden_prefixes = (
        "fastapi",
        "sqlalchemy",
    )
    violations: list[str] = []

    for path in roots:
        rel = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module.startswith(forbidden_prefixes):
                    violations.append(rel)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefixes):
                        violations.append(rel)

    assert sorted(set(violations)) == []


def test_api_catalog_stubs_do_not_map_to_executable_modules() -> None:
    registry_path = APP_ROOT / "core" / "registry.py"
    source = registry_path.read_text()

    assert "_TRAINER_EXECUTABLE_MODULES" not in source
    assert "_PREDICTOR_EXECUTABLE_MODULES" not in source


def test_runtime_compat_is_only_imported_by_prefect_flow_or_runtime_code() -> None:
    allowed_control_plane_importers = {
        "modules/prediction/flows/predict_job.py",
        "modules/training/flows/train_job.py",
    }
    violations: list[str] = []

    for path in _python_files(APP_ROOT):
        rel = _relative(path)
        if rel.startswith("runtime_compat/") or "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        imports_runtime_compat = any(
            (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("app.runtime_compat")
            )
            or (
                isinstance(node, ast.Import)
                and any(
                    alias.name.startswith("app.runtime_compat")
                    for alias in node.names
                )
            )
            for node in ast.walk(tree)
        )
        if imports_runtime_compat and rel not in allowed_control_plane_importers:
            violations.append(rel)

    assert sorted(set(violations)) == []


def test_api_registration_barrel_does_not_import_runtime_compat() -> None:
    path = APP_ROOT / "registrations.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert not any(
        module.startswith("app.runtime_compat") for module in imported_modules
    )


def test_api_main_import_does_not_load_optional_ml_runtime() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import app.main; "
                "forbidden = sorted("
                "name for name in sys.modules "
                "if name == 'app.runtime_compat' "
                "or name.startswith('app.runtime_compat.') "
                "or name == 'ml_library' "
                "or name.startswith('ml_library.') "
                "or name == 'torch' "
                "or name.startswith('torch.') "
                "or name == 'torchvision' "
                "or name.startswith('torchvision.') "
                "or name == 'ultralytics' "
                "or name.startswith('ultralytics.')); "
                "assert not forbidden, forbidden"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert probe.returncode == 0, probe.stderr
