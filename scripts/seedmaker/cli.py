#!/usr/bin/env python3
"""Unified seed CLI for the platform.

Usage::

    make seed ARGS="--list"
    make seed ARGS="mock-multi-image"
    make seed ARGS="mock-multi-image --max-samples 5000 --loader s3-zip"

Or via the seedmaker command::

    seedmaker --list
    seedmaker mock-multi-image
    seedmaker imagenet-mock
"""

from __future__ import annotations

import argparse
import sys

from seedmaker import registry
from seedmaker import datasets  # noqa: F401 — triggers auto-registration


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified seed CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--compose-file", default="infra/compose/docker-compose.yaml")
    parser.add_argument("--no-promote", action="store_true")
    parser.add_argument("--list", action="store_true", help="List available datasets")
    parser.add_argument(
        "--loader",
        default="dataset",
        choices=["dataset", "s3-zip"],
        help="Output loader (default: dataset)",
    )
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--large-samples", type=int, default=None)
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--images-per-sample", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--batch-report", type=int, default=None)
    parser.add_argument("--classification-samples", type=int, default=180)
    parser.add_argument("--review-samples", type=int, default=96)
    parser.add_argument("--sc-samples", type=int, default=2500)
    parser.add_argument("--sc-annotations", type=int, default=96)
    parser.add_argument("--sc-inspection-time", default=None)
    parser.add_argument("--zip-samples", type=int, default=500)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--s3-bucket", default="finetune-preview")
    parser.add_argument("--s3-prefix", default="")
    parser.add_argument("--no-model", action="store_true", help="Skip model creation")
    parser.add_argument(
        "--no-samples", action="store_true", help="Skip sample creation"
    )
    parser.add_argument(
        "--org-name",
        default=None,
        help="Override organization name (default: Default Org)",
    )
    parser.add_argument(
        "--org-slug",
        default=None,
        help="Override organization slug (default: default-org)",
    )
    parser.add_argument(
        "--job-timeout",
        type=int,
        default=60,
        help="Max seconds to wait for training job (default: 60)",
    )
    parser.add_argument("dataset", nargs="?", default="")

    args = parser.parse_args()

    if args.list:
        datasets_list = registry.list_datasets()
        if not datasets_list:
            print("No datasets registered.")
            return 0
        print(f"{'NAME':<25} {'DATASET':<35} DESCRIPTION")
        print("-" * 90)
        for name, ds_name, desc in datasets_list:
            print(f"{name:<25} {ds_name:<35} {desc}")
        return 0

    if not args.dataset:
        print("ERROR: specify a dataset name or use --list")
        print('Usage: make seed ARGS="<dataset> [--max-samples N] ..."')
        return 1

    entry = registry.get(args.dataset)
    if entry is None:
        print(
            f"ERROR: unknown dataset '{args.dataset}'. Use --list to see available datasets."
        )
        return 1

    config, run_fn = entry

    if args.org_name:
        config.org_name = args.org_name
    if args.org_slug:
        config.org_slug = args.org_slug
    config.compose_file = args.compose_file

    from seedmaker import SeedRunner

    runner = SeedRunner(config, api_url=args.api_url, no_promote=args.no_promote)
    runner.setup(skip_dataset=config.defer_dataset)

    return run_fn(args, runner)


if __name__ == "__main__":
    sys.exit(main())
