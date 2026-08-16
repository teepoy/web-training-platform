# ADR 0007: Typed membership rules and separate backfill

**Status:** Accepted (2026-08-15)

## Context

Collection membership discovery needs to express provider-specific conditions such as SC layer, device, lot, or inspection time without exposing SQL, JSONPath, or Python expressions. Rule activation also must not unexpectedly import a large historical population. Manual members and rule-discovered members share one Collection, so overlapping rules must not create duplicate members inside that Collection.

Discovery, incremental prediction, and candidate training have different resource costs and prerequisites. A single all-or-nothing switch would prevent users from maintaining dynamic membership without also consuming prediction or training resources.

## Decision

- Every Source provider descriptor declares its filterable fields, field types, allowed operators, and display metadata.
- A membership rule stores a validated, versioned generic `All/Any` condition tree. Raw SQL, JSONPath, Python, or unregistered provider fields are not accepted.
- One membership rule binds exactly one Source connector and one explicit Import profile. Cross-source behavior uses separate rules.
- Activating a membership rule processes only Source records first observed after activation. Historical discovery is a separate Backfill operation.
- Editing an active rule creates a new immutable rule version. Existing admitted members remain; historical evaluation under the new version requires an explicit Backfill.
- Pausing a rule does not silently consume its discovery cursor. On resume, the UI previews records observed during the pause and requires the user to choose plain-language `Catch up missed data` or `Only future data`; the latter advances from the chosen resume boundary without importing the paused interval.
- Inside one Collection, overlapping rules that match the same provider-owned Source record produce one Dataset/member and attach all matching rule provenance. Different Collections may import their own Dataset from the same Source record.
- Membership discovery, prediction of newly admitted members, and cron-gated Candidate training are separate Automation recipes with separate enablement and prerequisites.

Historical processing follows ADR 0008 and does not introduce a first-class Partition domain concept.

## Consequences

- Rule-builder controls are generated from the Source provider descriptor and can use user-facing field names such as Layer without hardcoding SC fields in the generic Collection UI.
- API validation and source query adapters share one versioned condition contract rather than accepting arbitrary executable expressions.
- Rule activation has bounded, understandable behavior; users request historical work separately.
- Collection-level Source record deduplication is distinct from per-rule replay receipts: one prevents duplicate members across overlapping rules, while the other makes each rule's event processing idempotent.
- Prediction and training can be enabled, paused, or unavailable without disabling membership discovery.
