from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a command with a hard timeout and TERM/KILL escalation.",
    )
    parser.add_argument(
        "--timeout", type=float, required=True, help="Timeout in seconds"
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required")
    return args


def main() -> int:
    args = parse_args()
    process = subprocess.Popen(args.command)

    try:
        return process.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGTERM)

    try:
        return process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
