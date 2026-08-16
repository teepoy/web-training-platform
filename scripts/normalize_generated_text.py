from __future__ import annotations

import argparse
from pathlib import Path


def normalize_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    normalized = (
        "\n".join(line.rstrip(" \t") for line in original.splitlines()).rstrip("\n")
        + "\n"
    )
    if normalized == original:
        return False
    path.write_text(normalized, encoding="utf-8")
    return True


def iter_files(paths: list[Path], suffix: str) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(
                candidate
                for candidate in path.rglob(f"*{suffix}")
                if candidate.is_file()
            )
        elif path.is_file() and path.name.endswith(suffix):
            files.add(path)
    return sorted(files)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize generated text files to exactly one trailing newline."
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--suffix", required=True)
    args = parser.parse_args()

    changed = sum(normalize_file(path) for path in iter_files(args.paths, args.suffix))
    print(f"Normalized {changed} generated file(s)")


if __name__ == "__main__":
    main()
