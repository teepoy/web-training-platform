# Development Tooling Guide

This tree is the single ownership boundary for executable mock, seed,
simulator, synthetic-data, and fake-kernel benchmark implementations.

## Package map

| Area           | Path                               | Role                                                                                            |
| -------------- | ---------------------------------- | ----------------------------------------------------------------------------------------------- |
| Seedmaker      | `devtools/seedmaker`               | Platform seed recipes, synthetic artifacts, and legacy compatibility seeders                    |
| Upstream mock  | `devtools/upstream-mock`           | Disposable Next.js upstream behavior service, dashboard, PostgreSQL state, control API, and CLI |
| SC dev adapter | `devtools/sc-upstream-dev-adapter` | Development-only HTTP bridge injected into the separate production SC upstream service          |
| Benchmarks     | `devtools/benchmarks`              | Development performance harnesses and fake compute kernels                                      |

## Boundaries

- Production `apps/*/src`, `apps/api/app`, `services/*/src`, and `libs/*/src`
  must not import `devtools`, `seedmaker`, simulator, mock, fake, fixture, or
  synthetic implementations.
- Development tools may import stable production contracts and clients. The
  dependency direction never runs from production code back into this tree.
- Test-only mocks remain valid under explicit `tests`, `e2e/mocks`, and
  `src/testing` roots; do not move them into production source packages.
- The upstream mock has its own Node package and container. Production
  Dockerfiles must not copy its metadata or source. Its development adapter is
  packaged only by its devtools-owned Dockerfile.
- Compatibility wrappers may remain under `scripts/`, but they must contain no
  mock or seed implementation.

## Verification

- Run `make test-seed-tools` after seedmaker changes.
- Run `pnpm --filter @devtools/upstream-mock test` and
  `PYTHONPATH=devtools/sc-upstream-dev-adapter/src uv run --package sc-upstream pytest devtools/sc-upstream-dev-adapter/tests`.
- Run `make check-config` after changing development Compose wiring.
- Keep production release manifests free of `devtools/` paths and mock
  services.
