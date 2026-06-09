#!/usr/bin/env python3
"""Thin backward-compatible wrapper around seedmaker CLI.

Usage::

    make seed ARGS="--list"
    make seed ARGS="mock-multi-image"
    make seed ARGS="imagenet-mock"
"""

from __future__ import annotations

import sys

from seedmaker.cli import main

if __name__ == "__main__":
    sys.exit(main())
