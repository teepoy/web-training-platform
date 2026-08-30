#!/usr/bin/env python3
"""Reject untranslated user-visible copy in production web sources."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCOPES = (ROOT / "apps/web/src",)
EXCLUDED_NAMES = {"HandbookPage.vue"}
EXCLUDED_PARTS = {"__tests__", "generated", "legacy", "sandbox", "templates", "testing"}
STATIC_ATTRIBUTE = re.compile(
    r"(?<![:@\w-])(aria-label|alt|placeholder|title|label|tab|description)\s*=\s*([\"'])(.*?)\2",
    re.DOTALL,
)
LETTER = re.compile(r"[A-Za-z]")
ALLOWED_TECHNICAL_VALUES = {
    '{"key": "value"}',
    "e.g. imported-dataset",
    "e.g. s3://bucket/img1.jpg, s3://bucket/img2.jpg",
    "you@example.com",
}
SCRIPT_VISIBLE_PATTERNS = (
    re.compile(
        r"\bmessage\.(?:success|error|warning|info|loading)\(\s*([\"'`])(.*?)\1",
        re.DOTALL,
    ),
    re.compile(r"\btoUserMessage\([^,\n]+,\s*([\"'`])(.*?)\1"),
    re.compile(
        r"\b(?:errorMessage|statusMessage|trainPredictStatusMessage)\.value\s*=\s*"
        r"([\"'`])(.*?)\1",
        re.DOTALL,
    ),
)


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
    template = template_source(source) if path.suffix == ".vue" else ""
    findings: list[tuple[int, str]] = []

    for match in STATIC_ATTRIBUTE.finditer(template):
        value = " ".join(match.group(3).split())
        if LETTER.search(value) and value not in ALLOWED_TECHNICAL_VALUES:
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

    for pattern in SCRIPT_VISIBLE_PATTERNS:
        for match in pattern.finditer(source):
            value = " ".join(match.group(2).split())
            if not value or not LETTER.search(value):
                continue
            findings.append(
                (
                    source.count("\n", 0, match.start()) + 1,
                    f"script-visible text: {value}",
                )
            )

    return findings


def source_files() -> list[Path]:
    return sorted(
        path
        for scope in SCOPES
        for pattern in ("*.vue", "*.ts")
        for path in scope.rglob(pattern)
        if path.name not in EXCLUDED_NAMES
        and not path.name.endswith(".spec.ts")
        and not path.name.endswith(".stories.ts")
        and not path.name.endswith(".design.vue")
        and not path.name.endswith(".stories.vue")
        and not any(part in EXCLUDED_PARTS for part in path.parts)
    )


def main() -> int:
    failed = False
    for path in source_files():
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
