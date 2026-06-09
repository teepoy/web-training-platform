# tests/scripts

Node scripts that run outside the test runner.

## check-parity.ts

Validates the test migration map at `tests/migration-map.md`.

```bash
# Print status counts (always exits 0 if parsing succeeds)
npx tsx tests/scripts/check-parity.ts --dry-run

# Fail if any test rows are still pending (ci gate)
npx tsx tests/scripts/check-parity.ts --strict

# Validate and enforce (fail on pending + missing files)
npx tsx tests/scripts/check-parity.ts --dry-run --strict
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | All clean (dry-run always 0; strict = 0 when all rows `migrated` or `dropped`) |
| 1 | `--strict` found `pending` rows, or validation errors exist |
| 2 | Unable to parse `migration-map.md` or file missing |

### Validation rules

1. Every `old_path` exists on disk for `pending` rows (warns if missing)
2. Every `new_path` exists on disk for `migrated` rows (errors if missing)
3. Every `dropped` row has non-empty `notes`
