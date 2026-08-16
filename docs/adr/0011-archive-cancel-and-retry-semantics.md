# ADR 0011: Archive, cancellation, and retry preserve provenance

**Status:** Accepted (2026-08-15)

## Context

Dataset and Collection resources accumulate Snapshots, Prediction Jobs, Models, Discovery receipts, and automation history. Physical deletion or transactional rollback across those records and external runtimes would break provenance or imply guarantees the platform cannot reliably provide. Retry also becomes ambiguous if a changed rule, Model, or Snapshot is silently substituted into the original run.

## Decision

- The ordinary removal action archives a Dataset or Collection. Archiving stops new target-bound automation while preserving Snapshots, run history, provenance, and existing results.
- Restoring an archived resource does not resume its Resource automations. Each automation remains paused until a user reviews and resumes it explicitly.
- Permanent deletion is an administrator operation and is allowed only when the platform verifies that no retained resource or run references the target.
- The first phase performs no age-based automatic purge of archived resources. Any future retention policy requires a separate decision covering Snapshot, Model, run, and source provenance references.
- Cancelling a Backfill or batch operation stops creation of new child work and requests best-effort cancellation of work already dispatched. Completed imports, Snapshots, and prediction results remain; the parent records `Cancelled with partial results` when applicable.
- Retry processes only failed or unfinished child items and preserves the original run's pinned rule version, Source connector, Import profile, Model, and Snapshot inputs.
- Running equivalent work with current configuration creates a new run rather than mutating the original run or calling it Retry.

## Consequences

- Cancellation is forward-stopping, not an unreliable distributed rollback.
- Parent runs must expose completed, failed, active, skipped, and cancelled child counts so partial results are understandable.
- Retry remains auditable and idempotent because its processing scope and pinned inputs do not change.
- Restoration is safe against surprise execution, and storage reclamation remains an explicit administrator action rather than a hidden time-based default.
