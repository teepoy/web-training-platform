# Seedmaker

This directory owns repository-wide development seed recipes, synthetic data,
fixture artifacts, and compatibility seeders. It is deliberately outside all
production application and service source roots.

Use the backward-compatible wrapper from the repository root:

```bash
uv run python scripts/seed.py --list
uv run python scripts/seed.py <recipe>
```

The SC showcase recipe calls the separately packaged simulator's authenticated
HTTP scenario. The legacy SQLite compatibility command remains explicitly
named and isolated:

```bash
PYTHONPATH=devtools uv run --package sc-upstream \
  python -m seedmaker.legacy_sc_sqlite --help
```

Production code may not import `seedmaker`. Tests can opt in through the
explicit `devtools` Python path.
