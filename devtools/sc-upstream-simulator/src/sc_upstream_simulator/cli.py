from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import os
from pathlib import Path
import sys
from typing import Any

import httpx


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _load_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("request file must contain one JSON object")
    return value


def _identity(args: argparse.Namespace) -> dict[str, object]:
    return {
        "wafer_key": args.wafer_key,
        "inspection_time": args.inspection_time,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control the development-only SC upstream simulator over HTTP"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "append", "update"):
        command = commands.add_parser(name)
        command.add_argument("--file", required=True, help="JSON request body")

    publish = commands.add_parser("publish")
    publish.add_argument("--wafer-key", required=True, type=int)
    publish.add_argument("--inspection-time", required=True)
    publish.add_argument("--published-at", required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("--wafer-key", required=True, type=int)
    inspect.add_argument("--inspection-time", required=True)

    list_command = commands.add_parser("list")
    list_command.add_argument("--state", choices=("draft", "published"))

    scenario = commands.add_parser(
        "dev-showcase",
        help="Publish the deterministic baseline and Gallery inspections",
    )
    scenario.add_argument("--file", required=True, help="JSON scenario request body")
    return parser


def _request(args: argparse.Namespace) -> tuple[str, str, dict[str, Any] | None]:
    if args.command == "create":
        return "POST", "/api/v1/inspections", _load_json(args.file)
    if args.command == "append":
        return "POST", "/api/v1/inspections/records", _load_json(args.file)
    if args.command == "update":
        return "PATCH", "/api/v1/inspections", _load_json(args.file)
    if args.command == "publish":
        return (
            "POST",
            "/api/v1/inspections/publish",
            {**_identity(args), "published_at": args.published_at},
        )
    if args.command == "inspect":
        return "POST", "/api/v1/inspections/inspect", _identity(args)
    if args.command == "list":
        path = "/api/v1/inspections"
        if args.state:
            path = f"{path}?state={args.state}"
        return "GET", path, None
    if args.command == "dev-showcase":
        return "POST", "/api/v1/scenarios/dev-showcase", _load_json(args.file)
    raise AssertionError(f"unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    base_url = _required_environment("SC_SIMULATOR_API_URL").rstrip("/")
    token = _required_environment("SC_SIMULATOR_API_TOKEN")
    timeout_seconds = float(_required_environment("SC_SIMULATOR_HTTP_TIMEOUT_SECONDS"))
    if timeout_seconds <= 0:
        raise ValueError("SC_SIMULATOR_HTTP_TIMEOUT_SECONDS must be positive")
    method, path, body = _request(args)
    with httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout_seconds,
    ) as client:
        response = client.request(method, path, json=body)
    if response.is_error:
        print(response.text, file=sys.stderr)
        return 1
    if response.status_code != 204:
        print(json.dumps(response.json(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
