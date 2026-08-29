#!/usr/bin/env python3
"""Reject untranslated static copy in the final i18n migration scope."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCOPES = (
    ROOT / "apps/web/src/features/sc",
    ROOT / "apps/web/src/shared/components",
)
EXCLUDED_NAMES = {"HandbookPage.vue"}
EXCLUDED_PARTS = {"legacy", "generated", "sandbox"}
STATIC_ATTRIBUTE = re.compile(
    r"(?<![:@\w-])(aria-label|alt|placeholder|title|label|tab|description)\s*=\s*([\"'])(.*?)\2",
    re.DOTALL,
)
LETTER = re.compile(r"[A-Za-z]")


def template_source(source: str) -> str:
    match = re.search(r"<template(?:\s[^>]*)?>(.*?)</template>", source, re.DOTALL)
    if not match:
        return ""
    return re.sub(r"<!--.*?-->", "", match.group(1), flags=re.DOTALL)


def text_only(template: str) -> str:
    """Blank tags while preserving text and source line positions."""
    result: list[str] = []
    in_tag = False
    quote: str | None = None
    for character in template:
        if in_tag:
            if quote:
                if character == quote:
                    quote = None
            elif character in {'"', "'"}:
                quote = character
            elif character == ">":
                in_tag = False
            result.append("\n" if character == "\n" else " ")
        elif character == "<":
            in_tag = True
            result.append(" ")
        else:
            result.append(character)
    return "".join(result)


def violations(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8")
    template = template_source(source)
    findings: list[tuple[int, str]] = []

    for match in STATIC_ATTRIBUTE.finditer(template):
        value = " ".join(match.group(3).split())
        if LETTER.search(value):
            findings.append(
                (
                    template.count("\n", 0, match.start()) + 1,
                    f"static {match.group(1)}: {value}",
                )
            )

    text_template = re.sub(
        r"{{.*?}}",
        lambda match: "".join("\n" if char == "\n" else " " for char in match.group()),
        text_only(template),
        flags=re.DOTALL,
    )
    for match in re.finditer(r"[^\n]+", text_template):
        value = " ".join(match.group().split())
        visible_value = re.sub(r"&[A-Za-z]+;", "", value)
        if not visible_value or not LETTER.search(visible_value):
            continue
        findings.append(
            (template.count("\n", 0, match.start()) + 1, f"static text: {value}")
        )

    return findings


def vue_files() -> list[Path]:
    return sorted(
        path
        for scope in SCOPES
        for path in scope.rglob("*.vue")
        if path.name not in EXCLUDED_NAMES
        and not path.name.endswith(".design.vue")
        and not any(part in EXCLUDED_PARTS for part in path.parts)
    )


def main() -> int:
    failed = False
    for path in vue_files():
        for template_line, message in violations(path):
            failed = True
            relative = path.relative_to(ROOT)
            print(f"{relative}:template+{template_line}: {message}")
    if failed:
        print(
            "Translate the copy with vue-i18n or move intentionally English documentation to the handbook."
        )
        return 1
    print("Web i18n literal check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
