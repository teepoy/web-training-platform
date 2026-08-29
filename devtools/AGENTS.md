# Development Tooling Guide

This tree is the single ownership boundary for executable mock, seed,
simulator, synthetic-data, and fake-kernel benchmark implementations.

## Package map

| Area | Path | Role |
| --- | --- | --- |
| Seedmaker | `devtools/seedmaker` | Platform seed recipes, synthetic artifacts, and legacy compatibility seeders |
| SC simulator | `devtools/sc-upstream-simulator` | Development-only PostgreSQL upstream simulator, control API, CLI, and migrations |
| Benchmarks | `devtools/benchmarks` | Development performance harnesses and fake compute kernels |

## Boundaries

- Production `apps/*/src`, `apps/api/app`, `services/*/src`, and `libs/*/src`
  must not import `devtools`, `seedmaker`, simulator, mock, fake, fixture, or
  synthetic implementations.
- Development tools may import stable production contracts and clients. The
  dependency direction never runs from production code back into this tree.
- Test-only mocks remain valid under explicit `tests`, `e2e/mocks`, and
  `src/testing` roots; do not move them into production source packages.
- The SC simulator has its own project lock and container. It is not a root uv
  workspace member, and production Dockerfiles must not copy its metadata or
  source.
- Compatibility wrappers may remain under `scripts/`, but they must contain no
  mock or seed implementation.

## Verification

- Run `make test-seed-tools` after seedmaker changes.
- Run the simulator tests with
  `uv run --project devtools/sc-upstream-simulator pytest devtools/sc-upstream-simulator/tests`.
- Run `make check-config` after changing development Compose wiring.
- Keep production release manifests free of `devtools/` paths and simulator
  services.
