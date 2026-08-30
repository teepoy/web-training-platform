# Development Tooling Guide

This tree is the single ownership boundary for executable mock, seed,
simulator, synthetic-data, and fake-kernel benchmark implementations.

## Package map

| Area           | Path                               | Role                                                                                            |
| -------------- | ---------------------------------- | ----------------------------------------------------------------------------------------------- |
| Test fixtures  | `devtools/seedmaker`               | Test-only synthetic builders and explicitly named legacy compatibility fixtures                 |
| Benchmarks     | `devtools/benchmarks`              | Development performance harnesses and fake compute kernels                                      |

## Boundaries

- Production `apps/*/src`, `apps/api/app`, `services/*/src`, and `libs/*/src`
  must not import `devtools`, `seedmaker`, simulator, mock, fake, fixture, or
  synthetic implementations.
- Development tools may import stable production contracts and clients. The
  dependency direction never runs from production code back into this tree.
- Test-only mocks remain valid under explicit `tests`, `e2e/mocks`, and
  `src/testing` roots; do not move them into production source packages.
- Standalone disposable tools own their dependency locks, documentation,
  generation, formatting, tests, and container build contexts. They are not
  root workspace members. Production Dockerfiles must not copy their metadata
  or source.
- There is no repository-wide operational seed CLI. Platform identities and
  resources use explicit administration and real product flows.

## Verification

- Run each standalone tool's checks from its own directory.
- Run `make check-config` after changing development Compose wiring.
- Keep production release manifests free of `devtools/` paths and mock
  services.
