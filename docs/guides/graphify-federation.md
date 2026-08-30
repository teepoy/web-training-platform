# Graphify Federation

This monorepo uses bounded, vertical Graphify graphs instead of one graph per deployable app or one graph for the entire repository. The boundary follows the conclusion recorded in task `01a00988-3053-76f0-855b-bf0ba93519aa`: a useful graph must keep a business flow together across API, Web, runtime services, and libraries without turning generic infrastructure symbols into global hubs.

## Graph layout

The tracked contract is `graphify/federation.json`. Generated graphs remain local under `graphify-out/`.

| Context                  | Primary questions                                                                   |
| ------------------------ | ----------------------------------------------------------------------------------- |
| `architecture-contracts` | Composition, ports, registries, OpenAPI/protobuf, data-plane and runtime boundaries |
| `data-resources`         | Dataset, storage, Collection, Revision, and Library                                 |
| `ml-lifecycle`           | Model, training, prediction, jobs, Prefect dispatch, and artifacts                  |
| `sc-domain`              | SC inspection, review sampling, image parsing, upstream data, and SC ML             |
| `ingestion-automation`   | Resource automation, source discovery, Backfill, schedules, and admission           |
| `platform-access`        | Authentication, organization context, admin, settings, and dashboard                |
| `agent-surface`          | Agent chat, display surfaces, widgets, descriptors, and registration                |

`graphify-out/graph.json` is intentionally the small `architecture-contracts` navigation graph. Each detailed graph is written to `graphify-out/contexts/<context>/graph.json`. This keeps the default architecture query useful while preserving deeper symbol-level graphs for focused questions.

The default graphs contain production code only. Tests, migrations, fixtures, and generated clients are diagnostic overlays and must be requested explicitly. This prevents generated DTOs, migration history, and test helpers from dominating centrality and community detection.

The manifest also carries a short, reviewable `noise_labels` list for generic extractor hubs such as `BaseModel` and `T`. Suppression is exact-label only and happens before clustering; adding an entry is an architecture-tooling decision, not an automatic popularity cutoff.

## Build and query

The repository pins Graphify `0.8.34` in the federation manifest because extraction and node-ID behavior affect graph reproducibility.

```bash
make graphify-check
make graphify-list
make graphify-build
```

The Make target defaults to one AST worker because sandboxed macOS environments can deny the process-pool semaphore probe. A normal host can opt into parallel extraction explicitly with `make graphify-build GRAPHIFY_MAX_WORKERS=6`.

Rebuild one context after a focused change:

```bash
make graphify-build ARGS="--context sc-domain"
```

The builder uses Graphify's deterministic AST cache, so the same command is also the incremental update path. Re-running a context reselects the tracked corpus and removes files that no longer belong to it; it does not depend on the previous graph's file list.

Query a context explicitly:

```bash
make graphify-query CONTEXT=sc-domain QUESTION='How does review sampling reach the SQL workbench?'
make graphify-query CONTEXT=architecture-contracts QUESTION='Trace DatasetStorageAgg to artifact commit'
```

If the owning context is unclear, use the deterministic alias router. It recommends contexts but never silently runs a query against a guessed graph:

```bash
python3 scripts/graphify_federation.py route 'How is a Collection Backfill admitted?'
```

Opt into a diagnostic overlay only for the context that defines it:

```bash
make graphify-build ARGS="--context sc-domain --overlay tests"
make graphify-build ARGS="--context architecture-contracts --overlay generated-contracts"
python3 scripts/graphify_federation.py query --context sc-domain --overlay tests 'Which test covers the sampler?'
```

Overlay graphs are written below `graphify-out/contexts/<context>/overlays/`; they never replace the production-code context graph or the root architecture graph.

After a complete build, validate generated graph direction, context metadata, and node limits:

```bash
make graphify-check ARGS="--graphs"
```

This validation also compares the tracked manifest hash and a content hash of every selected source/overlay file. A graph built from an older corpus fails as stale instead of being silently reused.

## Architecture contract graph

The architecture graph combines three sources:

1. Deterministic AST extraction of composition roots, ports, registries, runtime contracts, and frontend descriptors.
2. A reviewable semantic snapshot in `graphify/architecture-contracts.semantic.json`, extracted from `CORE_DESIGNS.md`, the repository `AGENTS.md` files, and selected architecture documents.
3. A curated bridge overlay in `graphify/architecture-bridges.json` for the cross-context paths that must stay navigable.

The bridge overlay explicitly preserves these paths:

- `DatasetStorageAgg` → data-plane manifest → registered runtime callable → artifact/prediction commit.
- `RuntimeRouter` → `RuntimeCapabilityCatalog` → `PrefectDeploymentSpec` → registered runtime callable.
- backend transport DTO → OpenAPI → generated Web client → frontend consumer.
- SC domain → protobuf → image parser → ML lifecycle.
- source admission → Data Resources / Collection Revision.

Graphify's graph merge operation does not discover new edges between independently extracted graphs. These bridges therefore belong in the small contract graph rather than in a blind merge of all context graphs.

## Maintaining the capability

When code moves inside an existing context, rebuild only that context. When a boundary, port, transport, or composition decision changes:

1. Update `graphify/federation.json` if ownership changed.
2. Update `graphify/architecture-bridges.json` when a cross-context path changed.
3. Refresh `graphify/architecture-contracts.semantic.json` only when its source documents changed. With `GEMINI_API_KEY` or `GOOGLE_API_KEY`, Graphify can perform the semantic extraction directly; without it, use the Graphify skill's semantic extraction agents.
4. Run `make test-graphify-federation`, `make graphify-check`, and rebuild the affected context plus `architecture-contracts`.
5. Inspect source counts and graph node counts. The manifest contains explicit per-context limits; crossing one is a boundary-review failure, not a reason to add a hidden fallback or silently truncate input.

Do not physically split the monorepo to improve Graphify results, do not make controller/domain/repository graphs, and do not publish a merged all-context graph as the default query surface.
