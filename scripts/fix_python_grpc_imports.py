from __future__ import annotations

import argparse
import re
from pathlib import Path


IMPORT_RE = re.compile(
    r"^from (?P<module>(?!proto_stubs\b)(?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*) "
    r"import (?P<import_name>[A-Za-z_]\w*_pb2\b.*)$",
    re.MULTILINE,
)


def fix_file(path: Path, package_prefix: str) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = IMPORT_RE.sub(
        lambda match: (
            f"from {package_prefix}.{match.group('module')} "
            f"import {match.group('import_name')}"
        ),
        original,
    )
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prefix grpcio-tools *_pb2_grpc.py imports with a Python package."
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("--package-prefix", default="proto_stubs")
    args = parser.parse_args()

    changed = 0
    for path in sorted(args.root.rglob("*_pb2_grpc.py")):
        if fix_file(path, args.package_prefix):
            changed += 1
    print(f"Fixed {changed} Python gRPC import file(s)")


if __name__ == "__main__":
    main()
