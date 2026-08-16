# ADR 0001: Context-first resource automation

**Status:** Accepted (2026-08-15)

## Context

The current product exposes Schedule, Sensor, and Sensor Subscription as separate user concepts. They represent different execution mechanisms, but an ordinary user's intent is normally resource-oriented: update a collection periodically, train after data changes, or run prediction when a resource is ready. Exposing the mechanisms as peer navigation entries makes users assemble the platform's internal model before they can express that intent.

## Decision

Automation authoring is context-first:

- Users create goal-specific automated actions from the Dataset, Dataset Collection, Model, or other target-resource page.
- Each resource type exposes a bounded list of product-defined automation recipes. Users do not assemble arbitrary trigger/action combinations.
- A global surface, if present, is for run status and history rather than the primary authoring entry point.
- The user-facing configuration describes a **run mode**. Time and event modes may keep separate internal trigger adapters; they are not forced into one generic backend trigger implementation.
- Event sources are registered by the system or configured by administrators. Ordinary users select only the event modes valid for the current resource and recipe; they do not create Sensors.
- When a cron trigger overlaps an active run of the same automation, the new occurrence is skipped and recorded. When event triggers overlap an active run, repeated events are coalesced into one pending rerun.
- Every first-phase automation is a first-class record with its own identity, lifecycle state, and history, but it requires exactly one target-resource binding and inherits that resource's authorization boundary.
- Archiving or deleting the target pauses future runs while preserving existing run history.
- Schedule, Sensor, and Subscription are implementation terminology, not peer concepts in the general-user navigation.
- The legacy `/schedules` and `/sensors` URLs will not receive compatibility redirects when the replacement information architecture is introduced.

This decision does not yet choose the supported action recipes, condition model, concurrency policy, retry policy, or operator-facing configuration surface.

## Consequences

- Resource pages must expose only automations that are meaningful for that resource and must explain them in goal-oriented language.
- A global surface may list and inspect automation records, status, pause state, and history; primary creation remains contextual to the required target resource.
- Every automation recipe must explicitly declare its supported resource types and run modes. A Prefect flow or arbitrary action is not automatically user-schedulable.
- Permissions and lifecycle behavior can be derived from the target resource instead of introducing a separate organization-wide automation ownership model.
- Existing schedule and sensor execution components may remain internally, but their APIs and persistence models must not dictate the user-facing information architecture.
- Event-source polling, checkpoints, and subscription dispatch remain internal integration concerns rather than general-user configuration concepts.
- Run history must expose skipped cron occurrences and coalesced event triggers; the concurrency behavior is product-visible rather than an implicit runtime default.
- Cross-resource and organization-level workflow orchestration is outside the first-phase model and requires a separate decision if introduced later.
- Removing the legacy routes can break saved bookmarks; the product accepts that cost instead of preserving the old mental model through redirects.
