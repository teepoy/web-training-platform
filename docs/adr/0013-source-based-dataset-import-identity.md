# ADR 0013: Source-based Dataset import identity

**Status:** Accepted (2026-08-15)

## Context

Dataset names are mutable display text, and the current SC path stores inspection time and wafer key only in JSON metadata, performs no database-enforced import uniqueness, and can create duplicates through concurrent or direct API requests. Automated discovery needs race-safe idempotency inside one automation chain, but product scope does not require content-based deduplication or Dataset sharing across Collections.

## Decision

- Every Source connector provides a stable opaque provider record key and, when source-change detection is supported, a Source version token. The platform combines connector ID and provider key as Source record identity; connectors that cannot provide a version signal explicitly do not support automatic source-change detection.
- A Dataset import identity combines the target Resource automation or Collection import scope, Source record identity, Source version, and Import profile version. Dataset name is not part of identity and need not be unique.
- A database uniqueness constraint reserves each identity within that import scope. An Import receipt owns staging and attempts: duplicate requests in the same automation chain attach to an active Import, reuse its Ready Dataset Revision result, or Retry the failed identity instead of creating another Dataset or Revision.
- A Dataset becomes Ready and generally visible only after its manifest and provenance are complete. Failed staging data never masquerades as a usable Dataset.
- Different Resource automations or Collections do not share their automatically imported Datasets, even when they read the same Source record with the same Import profile.
- The platform does not hash every image or compute a Dataset content fingerprint for duplicate detection. Manual uploads and different Source records are not content-deduplicated in this phase.
- Existing Dataset rows and metadata are not backfilled with the new import-identity fields. New automated imports use Import receipts; historical Datasets retain legacy provenance and are not guessed into an identity.

## Consequences

- The SC provider maps its composite upstream identity, currently inspection time plus wafer key, into the generic provider record key without leaking those fields into Collection logic.
- Application pre-checks remain useful for UI feedback, but database constraints and Import receipts provide the actual concurrency guarantee.
- Import status becomes separate from Dataset readiness, eliminating the current half-created Dataset failure mode.
- The uniqueness boundary intentionally prevents replay duplicates without introducing cross-Collection sharing, content normalization, or historical migration.
