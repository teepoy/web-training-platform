from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_ROOT = ROOT / "infra" / "compose"
PROFILE_OWNED_FIXED_ENVIRONMENT_KEYS = frozenset(
    {
        "LLM_MODEL",
        "MINIO_BUCKET",
        "REDIS_PORT",
    }
)
PROFILE_OWNED_FIXED_ENVIRONMENT_PREFIXES = (
    "PREDICTION_COMPACTION_",
    "SC_DATA_PROVIDER_",
    "SC_PIPELINE_",
)
DEPLOYMENT_OWNED_PROFILE_PREFIX_EXCEPTIONS = frozenset(
    {
        "SC_DATA_PROVIDER_CACHE_DIR",
        "SC_DATA_PROVIDER_CACHE_NAMESPACE",
    }
)
ENVIRONMENT_SPECIFIC_VALUES = frozenset(
    {
        "APP_CONFIG_PROFILE",
        "DATABASE_URL",
        "FRONTEND_URL",
        "JWT_SECRET_KEY",
        "LABEL_STUDIO_API_KEY",
        "LABEL_STUDIO_DATABASE_URL",
        "LABEL_STUDIO_EXTERNAL_URL",
        "LABEL_STUDIO_PASSWORD",
        "LABEL_STUDIO_USERNAME",
        "LABEL_STUDIO_USER_TOKEN",
        "MINIO_ACCESS_KEY",
        "MINIO_ROOT_PASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_SECRET_KEY",
        "OPERATOR_MINIO_CONSOLE_URL",
        "OPERATOR_PREFECT_UI_URL",
        "POSTGRES_PASSWORD",
        "POSTGRE_PASSWORD",
        "PREFECT_API_AUTH_STRING",
        "PREFECT_API_DATABASE_CONNECTION_URL",
        "PREFECT_SERVER_API_AUTH_STRING",
        "PREFECT_UI_URL",
        "SC_PATCH_S3_ACCESS_KEY",
        "SC_PATCH_S3_SECRET_KEY",
        "SC_REVIEW_S3_ACCESS_KEY",
        "SC_REVIEW_S3_SECRET_KEY",
    }
)


def _render(
    *files: Path,
    env_file: Path | None = None,
    profiles: tuple[str, ...] = (),
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    command = ["docker", "compose"]
    if env_file is not None:
        command.extend(("--env-file", str(env_file)))
    for compose_file in files:
        command.extend(("-f", str(compose_file)))
    for profile in profiles:
        command.extend(("--profile", profile))
    command.extend(("config", "--format", "json"))
    result = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, **(environment or {})},
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _normalized_volume(volume: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": volume.get("target"),
        "read_only": volume.get("read_only", False),
    }


def _normalized_environment(environment: dict[str, Any]) -> dict[str, Any]:
    return {
        key: "<environment-specific>" if key in ENVIRONMENT_SPECIFIC_VALUES else value
        for key, value in environment.items()
    }


def _normalized_service(service: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(service)

    # Expected environment-specific differences: release image location, local
    # build metadata, published acceptance ports, and host/named-volume sources.
    for key in ("build", "image", "ports", "pull_policy"):
        normalized.pop(key, None)

    normalized["environment"] = _normalized_environment(
        normalized.get("environment", {})
    )
    normalized["volumes"] = sorted(
        (_normalized_volume(volume) for volume in normalized.get("volumes", [])),
        key=lambda volume: (str(volume["target"]), volume["read_only"]),
    )

    # Pre-release may deliberately use lower resource ceilings. Reservations,
    # devices, and every other deploy behavior must remain production-shaped.
    deploy = normalized.get("deploy")
    if isinstance(deploy, dict):
        deploy = dict(deploy)
        resources = deploy.get("resources")
        if isinstance(resources, dict):
            resources = dict(resources)
            resources.pop("limits", None)
            if resources:
                deploy["resources"] = resources
            else:
                deploy.pop("resources", None)
        if deploy:
            normalized["deploy"] = deploy
        else:
            normalized.pop("deploy", None)

    return normalized


def _compare_project(
    name: str,
    production: dict[str, Any],
    pre_release: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    production_services = production.get("services", {})
    pre_release_services = pre_release.get("services", {})
    if set(production_services) != set(pre_release_services):
        errors.append(
            f"{name}: service sets differ: prod={sorted(production_services)}, "
            f"pre-release={sorted(pre_release_services)}"
        )
        return errors

    for service_name in sorted(production_services):
        prod_service = _normalized_service(production_services[service_name])
        pre_service = _normalized_service(pre_release_services[service_name])
        if prod_service == pre_service:
            continue
        prod_json = json.dumps(prod_service, indent=2, sort_keys=True).splitlines()
        pre_json = json.dumps(pre_service, indent=2, sort_keys=True).splitlines()
        diff = "\n".join(
            difflib.unified_diff(
                prod_json,
                pre_json,
                fromfile=f"prod/{name}/{service_name}",
                tofile=f"pre-release/{name}/{service_name}",
                lineterm="",
            )
        )
        errors.append(diff)
    return errors


def _assert_release_boundaries(
    production_projects: tuple[dict[str, Any], ...],
    deployed_pre_release_projects: tuple[dict[str, Any], ...],
    local_pre_release_projects: tuple[dict[str, Any], ...],
) -> list[str]:
    errors: list[str] = []
    for project in production_projects:
        for service_name, service in project.get("services", {}).items():
            if service.get("ports"):
                errors.append(
                    f"prod/{service_name}: production services must not publish host ports"
                )
            if service.get("build"):
                errors.append(
                    f"prod/{service_name}: production services must use released images"
                )
            profile = service.get("environment", {}).get("APP_CONFIG_PROFILE")
            if profile is not None and profile != "prod":
                errors.append(
                    f"prod/{service_name}: expected APP_CONFIG_PROFILE=prod, "
                    f"got {profile!r}"
                )

    for project in deployed_pre_release_projects:
        for service_name, service in project.get("services", {}).items():
            if service.get("ports"):
                errors.append(
                    f"deployed-pre-release/{service_name}: deployed services "
                    "must not publish host ports"
                )
            if service.get("build"):
                errors.append(
                    f"deployed-pre-release/{service_name}: deployed services "
                    "must use released images"
                )
            profile = service.get("environment", {}).get("APP_CONFIG_PROFILE")
            if profile is not None and profile != "pre-release":
                errors.append(
                    f"deployed-pre-release/{service_name}: expected "
                    f"APP_CONFIG_PROFILE=pre-release, got {profile!r}"
                )

    for project in local_pre_release_projects:
        for service_name, service in project.get("services", {}).items():
            for port in service.get("ports", []):
                if port.get("host_ip") != "127.0.0.1":
                    errors.append(
                        f"pre-release/{service_name}: example acceptance ports "
                        "must bind to 127.0.0.1"
                    )
            profile = service.get("environment", {}).get("APP_CONFIG_PROFILE")
            if profile is not None and profile != "pre-release":
                errors.append(
                    f"pre-release/{service_name}: expected "
                    f"APP_CONFIG_PROFILE=pre-release, got {profile!r}"
                )
    return errors


def _assert_profile_owned_settings_not_exposed(
    projects: tuple[tuple[str, dict[str, Any]], ...],
) -> list[str]:
    errors: list[str] = []
    for project_name, project in projects:
        for service_name, service in project.get("services", {}).items():
            environment = service.get("environment", {})
            if "APP_CONFIG_PROFILE" not in environment:
                continue
            duplicates = {
                key
                for key in environment
                if (
                    key in PROFILE_OWNED_FIXED_ENVIRONMENT_KEYS
                    or key.startswith(PROFILE_OWNED_FIXED_ENVIRONMENT_PREFIXES)
                )
                and key not in DEPLOYMENT_OWNED_PROFILE_PREFIX_EXCEPTIONS
            }
            if duplicates:
                errors.append(
                    f"{project_name}/{service_name}: profile-owned settings must "
                    f"not be exposed through Compose environment: "
                    f"{', '.join(sorted(duplicates))}"
                )
    return errors


def main() -> int:
    production = COMPOSE_ROOT / "production"
    pre_release = COMPOSE_ROOT / "pre-release"

    dev = _render(
        COMPOSE_ROOT / "docker-compose.yaml",
        COMPOSE_ROOT / "docker-compose.dev.yaml",
        profiles=("ops",),
    )

    prod_stateful = _render(
        production / "compose.stateful.yaml",
        env_file=production / "env-stateful.example",
    )
    prod_platform = _render(
        production / "compose.platform.yaml",
        env_file=production / "env-platform.example",
        profiles=("*",),
        environment={"APP_CONFIG_PROFILE": "prod"},
    )
    prod_ops = _render(
        production / "compose.ops.yaml",
        env_file=production / "env-platform.example",
        profiles=("ops",),
        environment={"APP_CONFIG_PROFILE": "prod"},
    )
    prod_observability = _render(
        production / "compose.observability.yaml",
        env_file=production / "env-observability.example",
        profiles=("*",),
    )

    deployed_pre_stateful = _render(
        production / "compose.stateful.yaml",
        env_file=production / "env-stateful.example",
        environment={"PLATFORM_NETWORK_NAME": "finetune-pre-release"},
    )
    deployed_pre_platform = _render(
        production / "compose.platform.yaml",
        env_file=production / "env-platform.example",
        profiles=("*",),
        environment={
            "APP_CONFIG_PROFILE": "pre-release",
            "PLATFORM_NETWORK_NAME": "finetune-pre-release",
        },
    )
    deployed_pre_ops = _render(
        production / "compose.ops.yaml",
        env_file=production / "env-platform.example",
        profiles=("ops",),
        environment={
            "APP_CONFIG_PROFILE": "pre-release",
            "PLATFORM_NETWORK_NAME": "finetune-pre-release",
        },
    )
    deployed_pre_observability = _render(
        production / "compose.observability.yaml",
        env_file=production / "env-observability.example",
        profiles=("*",),
        environment={"PLATFORM_NETWORK_NAME": "finetune-pre-release"},
    )

    local_pre_stateful = _render(
        production / "compose.stateful.yaml",
        pre_release / "compose.stateful.yaml",
        env_file=pre_release / "env.example",
    )
    local_pre_platform = _render(
        production / "compose.platform.yaml",
        pre_release / "compose.build.yaml",
        pre_release / "compose.platform.yaml",
        env_file=pre_release / "env.example",
        profiles=("*",),
        environment={"APP_CONFIG_PROFILE": "pre-release"},
    )
    local_pre_ops = _render(
        production / "compose.ops.yaml",
        env_file=pre_release / "env.example",
        profiles=("ops",),
        environment={"APP_CONFIG_PROFILE": "pre-release"},
    )

    errors = [
        *_compare_project("deployed/stateful", prod_stateful, deployed_pre_stateful),
        *_compare_project("deployed/platform", prod_platform, deployed_pre_platform),
        *_compare_project("deployed/ops", prod_ops, deployed_pre_ops),
        *_compare_project(
            "deployed/observability",
            prod_observability,
            deployed_pre_observability,
        ),
        *_compare_project("local/stateful", prod_stateful, local_pre_stateful),
        *_compare_project("local/platform", prod_platform, local_pre_platform),
        *_compare_project("local/ops", prod_ops, local_pre_ops),
        *_assert_release_boundaries(
            (prod_stateful, prod_platform, prod_ops, prod_observability),
            (
                deployed_pre_stateful,
                deployed_pre_platform,
                deployed_pre_ops,
                deployed_pre_observability,
            ),
            (local_pre_stateful, local_pre_platform, local_pre_ops),
        ),
        *_assert_profile_owned_settings_not_exposed(
            (
                ("dev", dev),
                ("prod/platform", prod_platform),
                ("prod/ops", prod_ops),
                ("deployed-pre-release/platform", deployed_pre_platform),
                ("deployed-pre-release/ops", deployed_pre_ops),
                ("local-pre-release/platform", local_pre_platform),
                ("local-pre-release/ops", local_pre_ops),
            )
        ),
    ]
    if errors:
        print("Compose release parity check failed:", file=sys.stderr)
        for error in errors:
            print(f"\n{error}", file=sys.stderr)
        return 1

    print(
        "Compose release parity OK: deployed pre-release and prod use the same "
        "manifests and runtime semantics; local acceptance differences remain "
        "within the allowed boundary."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
