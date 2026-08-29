# Seedmaker

This directory owns repository-wide development seed recipes, synthetic data,
fixture artifacts, and compatibility seeders. It is deliberately outside all
production application and service source roots.

Use the backward-compatible wrapper from the repository root:

```bash
uv run python scripts/seed.py --list
uv run python scripts/seed.py <recipe>
```

SC artifact and legacy SQLite compatibility commands are invoked as modules so
their implementation remains inside this boundary:

```bash
PYTHONPATH=devtools uv run python -m seedmaker.sc_artifacts --help
PYTHONPATH=devtools uv run --package sc-upstream \
  python -m seedmaker.legacy_sc_sqlite --help
```

Production code may not import `seedmaker`. Tests can opt in through the
explicit `devtools` Python path.
