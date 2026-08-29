#!/usr/bin/env python3
"""Thin backward-compatible wrapper around seedmaker CLI.

Usage::

    make seed ARGS="--list"
    make seed ARGS="mock-multi-image"
    make seed ARGS="imagenet-mock"
"""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "devtools"))

from seedmaker.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
