# ADR 0012: Capability-based Collection data contract

**Status:** Accepted (2026-08-15)

## Context

Dataset type identifies an integration and storage behavior, but it does not fully describe whether two Datasets can be composed for a task. Different Dataset types may expose the same target view, task schema, and label semantics through adapters. Requiring identical type names would reject valid compositions, while accepting arbitrary members would postpone predictable failures until materialization, prediction, or training.

## Decision

- A Collection declares a data contract consisting of its target view, task schema, and canonical label space.
- Users select a product-defined Collection purpose such as Image Classification and its canonical labels. A descriptor resolves that choice to the underlying view and schema contract; ordinary users do not enter view IDs or raw schemas.
- Dataset adapters declare the views and schemas they can provide. A Dataset may join when an adapter can satisfy the Collection contract; identical `dataset_type` values are not required.
- A member whose labels differ may provide an explicit versioned mapping. Every source label must map to a canonical label or be explicitly marked `Ignore`, and the UI previews affected counts before publication; fuzzy or silent automatic mapping is not allowed.
- Changing the Collection contract or canonical labels creates a new definition
  version. Historical Revisions remain unchanged, and current members, rules,
  default Model, and training recipe compatibility are revalidated before the
  next publication or dispatch.
- A valid contract change may be saved and its compatible definition may still
  publish a Revision even when a previously configured Model or recipe becomes
  incompatible. Each affected binding is marked incompatible and paused
  independently until corrected; an old Model does not lock the Collection
  definition.
- If automatic discovery encounters a source label missing from the active mapping, admission stops at `Needs mapping` without publishing that member. Updating the mapping allows Retry of only the affected record; the platform never silently expands the canonical labels or ignores an unknown label.
- Samples whose source label is explicitly mapped to `Ignore` are excluded when
  current member data is resolved for classify or a job, while the source
  Dataset remains complete. Preflight reports the excluded sample count.
- Revision publication validates member capabilities and the output schema and
  label contract before making the Revision current.
- Default Models and candidate-training recipes are validated against the Collection data contract before configuration or dispatch, rather than waiting for runtime failure.
- Arbitrary heterogeneous membership with no shared contract is not supported.

## Consequences

- Existing view-oriented compatibility can evolve without hardcoding provider or Dataset-type pairs into Collection logic.
- Collection creation and member linking need a clear contract summary and actionable incompatibility reasons.
- Label mapping and contract versions become part of Collection Revision
  provenance, preserving historical task-definition semantics as the
  Collection evolves without claiming member-data replay.
