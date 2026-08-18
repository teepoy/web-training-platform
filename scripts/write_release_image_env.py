from __future__ import annotations

import argparse
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

_COMPONENTS = (
    ("FINETUNE_API_IMAGE", "api"),
    ("FINETUNE_WEB_IMAGE", "web"),
    ("FINETUNE_CPU_WORKER_IMAGE", "cpu-worker"),
    ("FINETUNE_GPU_WORKER_IMAGE", "gpu-worker"),
    ("SC_UPSTREAM_IMAGE", "sc-upstream"),
    ("IMAGE_PARSER_IMAGE", "image-parser"),
)
_REGISTRY_RE = re.compile(r"[a-z0-9.-]+(?::[0-9]+)?")
_REPOSITORY_SEGMENT_RE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _validate_registry(registry: str) -> str:
    if not _REGISTRY_RE.fullmatch(registry):
        raise ValueError("registry must be a lowercase registry host without a scheme")
    return registry


def _validate_repository(repository: str) -> str:
    segments = repository.split("/")
    if len(segments) < 2 or any(
        not _REPOSITORY_SEGMENT_RE.fullmatch(segment) for segment in segments
    ):
        raise ValueError("repository must be a lowercase owner/name path")
    return repository


def _parse_digest_assignments(assignments: Sequence[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    expected_components = {component for _, component in _COMPONENTS}
    for assignment in assignments:
        component, separator, digest = assignment.partition("=")
        if not separator or component not in expected_components:
            raise ValueError(f"invalid component digest assignment: {assignment}")
        if component in digests:
            raise ValueError(f"duplicate component digest: {component}")
        if not _DIGEST_RE.fullmatch(digest):
            raise ValueError(f"invalid sha256 digest for component: {component}")
        digests[component] = digest

    missing = expected_components - digests.keys()
    if missing:
        raise ValueError(f"missing component digests: {', '.join(sorted(missing))}")
    return digests


def render_release_image_env(
    *, registry: str, repository: str, digests: Mapping[str, str]
) -> str:
    registry = _validate_registry(registry)
    repository = _validate_repository(repository)
    validated_digests = _parse_digest_assignments(
        [f"{component}={digest}" for component, digest in digests.items()]
    )
    image_root = f"{registry}/{repository}"
    return "".join(
        f"{variable}={image_root}-{component}@{validated_digests[component]}\n"
        for variable, component in _COMPONENTS
    )


def validate_release_image_env(*, content: str, registry: str, repository: str) -> None:
    registry = _validate_registry(registry)
    repository = _validate_repository(repository)
    expected = {variable: component for variable, component in _COMPONENTS}
    observed: dict[str, str] = {}
    for line in content.splitlines():
        variable, separator, value = line.partition("=")
        if not separator or variable not in expected:
            raise ValueError(f"invalid release image entry: {line}")
        if variable in observed:
            raise ValueError(f"duplicate release image entry: {variable}")
        component = expected[variable]
        prefix = f"{registry}/{repository}-{component}@"
        if not value.startswith(prefix) or not _DIGEST_RE.fullmatch(
            value[len(prefix) :]
        ):
            raise ValueError(f"invalid digest reference for release image: {variable}")
        observed[variable] = value

    missing = expected.keys() - observed.keys()
    if missing:
        raise ValueError(f"missing release image entries: {', '.join(sorted(missing))}")


def write_release_image_env(
    *, output: Path, registry: str, repository: str, digests: Mapping[str, str]
) -> None:
    if not output.is_absolute():
        raise ValueError("output must be an absolute path")
    if not output.parent.is_dir():
        raise ValueError(f"output directory does not exist: {output.parent}")

    content = render_release_image_env(
        registry=registry,
        repository=repository,
        digests=digests,
    )
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.chmod(0o644)
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Atomically write immutable release image references."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--registry", default="ghcr.io")
    parser.add_argument("--repository", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--digest",
        action="append",
        metavar="COMPONENT=SHA256",
        help="repeat once for each release component",
    )
    mode.add_argument(
        "--validate-existing",
        action="store_true",
        help="validate an existing immutable release image file",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        if args.validate_existing:
            validate_release_image_env(
                content=args.output.read_text(encoding="utf-8"),
                registry=args.registry,
                repository=args.repository,
            )
        else:
            write_release_image_env(
                output=args.output,
                registry=args.registry,
                repository=args.repository,
                digests=_parse_digest_assignments(args.digest),
            )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
