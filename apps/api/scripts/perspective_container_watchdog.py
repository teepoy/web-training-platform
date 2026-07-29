from __future__ import annotations

import argparse
import os
import signal
import subprocess
from pathlib import Path
from types import FrameType
from typing import Sequence


def run_service(command: Sequence[str], pid_file: Path) -> int:
    child = subprocess.Popen(command, start_new_session=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(child.pid), encoding="utf-8")

    def forward_signal(signum: int, _frame: FrameType | None) -> None:
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGINT, forward_signal)
    signal.signal(signal.SIGTERM, forward_signal)

    try:
        return_code = child.wait()
    finally:
        pid_file.unlink(missing_ok=True)

    if return_code < 0:
        return 128 + abs(return_code)
    return return_code


def parse_args(argv: Sequence[str] | None = None) -> tuple[Path, tuple[str, ...]]:
    parser = argparse.ArgumentParser(
        description="Run Perspective as a child process so its healthcheck can force a container restart"
    )
    parser.add_argument(
        "--pid-file",
        type=Path,
        default=Path("/tmp/perspective-ws-service.pid"),
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = tuple(args.command)
    if command[:1] == ("--",):
        command = command[1:]
    if not command:
        parser.error("a service command is required after --")
    return args.pid_file, command


def main(argv: Sequence[str] | None = None) -> int:
    pid_file, command = parse_args(argv)
    return run_service(command, pid_file)


if __name__ == "__main__":
    raise SystemExit(main())
