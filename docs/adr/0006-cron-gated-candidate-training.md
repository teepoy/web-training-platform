# ADR 0006: Cron-gated candidate training

**Status:** Accepted (2026-08-15)

## Context

Training immediately on every Collection update can create overlapping expensive runs. Training on every cron occurrence even when data is unchanged wastes resources. Automatically promoting a successful training output can replace a known-good default Model with a regressed Model before evaluation safeguards exist.

The product needs an executable end-to-end training chain eventually, but model-regression safeguards, evaluation, and promotion policy are not designed deeply enough to make automatic training safe in the first implementation. The first implementation therefore records the intended policy as a follow-up contract and does not dispatch Collection training automatically.

## Decision

- Publishing a new current Collection Revision after membership, Collection
  definition, or mapping changes marks the automated-training binding dirty.
  Dataset Revision or upstream-value changes do not publish a Collection
  Revision and do not mark training dirty by themselves.
- A cron occurrence starts training only when the binding is dirty and the
  current Collection Revision differs from the Revision used by its last
  successful training run.
- Collection users configure the training window through product-level daily or weekly frequency, local time, and IANA timezone controls. The platform converts that choice to its trigger adapter representation; ordinary users do not enter raw cron expressions.
- Training records the concrete current Collection Revision selected at
  dispatch time and resolves current selected-member data. The Revision is
  definition provenance, not member-data replay.
- Every candidate-training recipe descriptor declares named readiness requirements such as supported Collection contract, minimum usable rows, and label coverage. Preflight shows each actual value and blocks unmet requirements; thresholds are not hidden global defaults.
- A successful run creates a Candidate Model and records its Collection
  Revision and training-run provenance.
- All Candidate Models are retained with their Collection Revision provenance.
  The UI may highlight the latest Candidate but does not overwrite or delete
  earlier Candidates.
- A Candidate Model never automatically replaces the pinned Collection default Model.
- The runnable candidate-training chain is deferred. Its implementation TODO includes evaluation, regression detection, comparison, approval, rollback analysis, and Promote semantics; none may be inferred from a successful training run.
- Overlapping cron occurrences follow the accepted automation policy: they are skipped and recorded rather than queued or run concurrently.
- A failed training run keeps the binding dirty but moves it to `Needs attention`. Later cron occurrences are skipped and recorded until a user explicitly retries or resolves the binding.

## Consequences

- The platform does not expose an unsafe partially designed automated-training path.
- A Collection update does not immediately consume training resources; cron provides the execution window.
- Candidate and default Model status must be visibly distinct in the UI and API.
- Failed configurations or data do not consume training resources again on every cron occurrence without an explicit recovery action.
- Promotion cannot be inferred from training success and requires a future accepted decision.
