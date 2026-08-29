# TODO: Legacy Configuration and Code Cleanup

## Progress

- **Overall status:** Complete.
- **Completed outcome:** configuration has one documented ownership model,
  tracked `prod.yaml` owns stable non-secret production behavior, environment
  variables own secrets and deployment topology, registries own executable
  categories, and Make/release inputs no longer provide competing application
  settings. Extra compatibility fields are ignored as approved.
- **Code cleanup:** the last live consumer of the retired classify package was
  moved into the dataset feature, the unregistered classify/preview legacy
  trees were deleted after a repository consumer audit, generic components use
  shared ownership, and unnecessary production `Sc*` Vue filenames are gone.
- **Verification:** repository searches find no production `@/legacy`, retired
  classify/preview route, or unnecessary `Sc*.vue` consumer; lint, all 516 web
  unit tests, the production web build, and the full browser regression suite
  pass.

This document tracks deferred cleanup of legacy configuration paths, duplicated
options, unused code, and unnecessary naming prefixes. It records work to be
investigated and does not authorize removing or changing runtime behavior before
the affected consumers and compatibility requirements are identified.

### Problems

1. Configuration is defined inconsistently through YAML files, Python code,
   command-line arguments, and environment variables.
2. Some environment variables and configuration options represent the same
   setting. Most settings should have one canonical definition and input path.
3. The repository contains unused code and names with unnecessary prefixes.

### Proposed Direction

Inventory configuration inputs and trace every definition to its consumers.
For each setting, select one canonical configuration mechanism based on its
ownership and runtime requirements. Remove duplicate aliases only after their
call sites, deployment manifests, documentation, and compatibility impact have
been reviewed.

Separately, identify code that is unreachable or has no supported consumer, and
identify prefixes that no longer disambiguate a real domain or subsystem
boundary. Treat deletion and renaming as reviewable changes with focused tests,
not as a broad mechanical sweep.

### Resolved Decisions

- Except for the settings scaffold and deployment/configuration surfaces,
  existing product behavior remains backward-compatible. Existing stored data
  may be read through compatibility adapters, but no bulk data backfill is
  required.
- Secrets belong only in environment variables. Stable non-secret application
  settings and limits belong in tracked YAML. Registries/descriptors remain the
  source for categories whose values are executable code or code-owned
  extension metadata.
- A setting has one owner and one supported input path. Environment precedence
  applies only during a short migration overlap or to explicitly environment-
  owned secret/deployment inputs; the target design does not retain duplicate
  YAML and environment options.
- Old environment-variable names are removed without aliases. This is an
  intentional deployment compatibility exception and must be called out in
  release/operator notes.
- `apps/api/config/prod.yaml` is the git-tracked, image-bundled source of truth
  for production's non-secret application configuration. Production startup
  reads that file directly; it must not depend on a generated, untracked, or
  host-mounted replacement file.
- Release documentation must name that tracked `prod.yaml` as the only source
  for non-secret production application settings. Remove any competing
  non-secret application source from release environment examples, generated
  release environment files, and operator instructions.
- Secret values are removed from `prod.yaml`, including empty secret
  placeholders where the loader can instead require the corresponding
  environment-owned value. Missing required secrets fail startup explicitly.
- Deployment mechanics such as image references, bind addresses, mounted
  paths, profile selection, and secret-bearing connection strings remain
  deployment/environment owned. The inventory must classify borderline values
  such as public endpoint URLs once, rather than expose them through both
  Compose and YAML.
- Prefix cleanup covers all unnecessary prefixes, including `Sc*` Vue component
  names under `features/sc`. Components whose behavior is domain-neutral move
  to shared ownership; genuinely SC-specific components receive concise names
  within the SC namespace.

### Work Items

- Catalog YAML, Python, command-line, and environment-based configuration by
  subsystem, owner, default value, override precedence, and consumer.
- Find settings represented by multiple environment variables or configuration
  options and designate one canonical name and source for each.
- During migration, document any temporary duplicate input and its removal
  point; do not preserve permanent multi-source configuration.
- Update affected call sites, deployment manifests, examples, and documentation
  before removing duplicate configuration paths.
- Update the repository's release/deployment documentation, specifically
  `docs/guides/production-compose-deployment.md` and
  `infra/compose/README.md`. Their environment examples may retain only secrets
  and deployment mechanics; non-secret application values must move to or point
  at `apps/api/config/prod.yaml`, and the current “environment overrides YAML”
  wording must be removed.
- Find unused modules, functions, classes, constants, configuration entries,
  arguments, and environment variables, then verify that they have no runtime,
  generated-code, plugin, or external consumer before deletion.
- Review naming prefixes and remove only those that do not communicate an
  ownership, protocol, domain, or compatibility boundary.
- Add or update tests that preserve intended behavior during each cleanup.
- Split implementation into subsystem-sized changes so regressions and
  compatibility decisions remain reviewable.

### Acceptance Criteria

- Every supported setting has a documented canonical name, source, owner, type,
  default policy, and override behavior.
- Tracked `prod.yaml` contains the complete stable non-secret production
  application configuration and no secret values; production consumes the
  bundled tracked file.
- Release documentation and generated release environment inputs do not define
  a second source for any `prod.yaml`-owned setting.
- Duplicate settings are removed unless multiple inputs are explicitly required
  and their precedence is documented and tested.
- Configuration errors are surfaced clearly; consolidation does not introduce
  silent fallback behavior or new implicit defaults.
- Removed code and configuration have been checked for internal, generated,
  deployment, plugin, and external consumers.
- Prefix removals preserve meaningful domain and subsystem distinctions.
- Relevant tests, generated artifacts, deployment manifests, examples, and
  documentation agree with the consolidated configuration contract.
- Cleanup changes comply with `CORE_DESIGNS.md` and the nearest subsystem
  `AGENTS.md` instructions.

### Current Implementation Status

The first API configuration consolidation slice is complete: tracked profile
YAML owns stable application behavior, environment inputs are limited to
secrets and deployment topology, and release Compose consumes the bundled
tracked `prod.yaml`. Root and modular Make targets were audited as part of this
slice. Host API, migration, administration, and worker targets now share one
development environment definition, and their frontend, platform API, and
MinIO endpoints derive from the canonical Make variables instead of repeating
hard-coded ports.

The agreed unused-code and prefix inventory is complete. The only similarly
named live route is `CollectionClassifyView.vue`, where “Classify” describes the
supported collection workflow rather than a retired prefix. Configuration
ownership is documented in `docs/architecture/configuration-ownership.md`.

### Before Implementation

Break this todo into an audited inventory and explicit subsystem-level cleanup
tasks. Preserve product behavior and compatibility reads without requiring
backfill. Settings and deployment inputs may break as explicitly recorded
above; publish their migration notes before deleting old names or changing
production configuration ownership.

Implementation is complete. New settings must be added to the ownership catalog
and exactly one canonical source; future dead-code removal remains normal
subsystem maintenance rather than an open item in this modernization goal.
