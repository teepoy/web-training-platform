# ADR 0009: Contextual automation information architecture

**Status:** Accepted (2026-08-15)

## Context

Schedule, Sensor, Subscription, Backfill, Prediction, and Training as peer pages force ordinary users to understand execution mechanisms before completing a Collection task. At the same time, Resource automation is a first-class record and needs a global surface for operational review and recovery.

Source connector configuration and infrastructure consoles require administrator access, while ordinary Collection users only need available connection choices and product-level health information.

## Decision

- Collection Detail groups work into `Data`, `Models`, `Revisions`, and
  `Activity`, plus a direct `Classify ↗` workspace navigation item. Classify
  does not render an intermediate preview pane and is not another Automation
  mechanism page.
- `Data` contains members, Membership rules, discovery status, and Backfill. `Models` contains the default Model, prediction coverage, reconciliation batches, Candidate Models, and cron-gated candidate training.
- Classify is a prominent direct workspace navigation item on the Collection, rather than an intermediate Samples surface or another mechanism-oriented automation section.
- A global sidebar `Automations` page lists target-bound Automation records across resources and supports filtering, inspection, pause/resume, Retry, and history. It does not provide a targetless generic creation builder.
- Discovery, Backfill, batch prediction, reconciliation, and training use one canonical run record. The same record appears with resource context in the target's `Activity` area and with cross-resource filters in the global `Automations` page.
- `Admin > Connections` manages Source connectors and Label Studio configuration. `Admin > Infrastructure` shows Prefect UI and MinIO Console configuration status and protected links.
- Org admins configure polling and reconciliation cadence on each Source connector. Ordinary users see `Last checked`, `Next check`, and `Check now` on their Membership rule without editing cron syntax.
- All members of the current organization may modify Collection Membership rules and Automation configuration and may trigger Backfill, prediction, reconciliation, and candidate training. Source connector and infrastructure configuration remain Org-admin-only.
- Backfill, bulk prediction reconciliation, and candidate training require an
  impact summary and explicit confirmation before submission. The summary
  identifies the target Collection, pinned rule/Model/Revision inputs, and the
  estimated child work rather than relying on administrator approval.
- If the target scope, pinned rule/Model/Revision, or estimated child-task count
  cannot be resolved, submission is blocked with an explicit reason. A
  compute-cost estimate may remain unavailable as long as the concrete work
  scope is known.
- Concurrent edits to Membership rules, Collection default Model bindings, and Resource automation configuration use optimistic version checks. A stale editor must resolve the conflict explicitly; the platform never silently applies last-write-wins behavior.
- Every mutation and manually triggered run records the acting user and organization for audit.
- First-phase failure awareness is in-product: notification center entries, sidebar attention state, and resource Activity surface `Failed`, `Partial`, and `Needs attention`. Notifications go to the initiating user and users who follow the target Collection or Automation, not every organization member. Email and webhook delivery are deferred until channel configuration and delivery policy are designed.
- A Collection creator follows it by default and may unfollow. The actor who starts a manual run receives that run's result without being silently subscribed to future Collection activity.
- Dataset Revision notifications may list affected Collections for operational
  awareness, but no Collection update review or republishing action is needed;
  consumers resolve current member data dynamically.

## Consequences

- Context pages teach business tasks while the global Automations page supports cross-resource operations.
- The current creator-only Collection mutation rule must be intentionally replaced by organization-member edit authorization; this is not a frontend-only change.
- Because all organization members can trigger resource-consuming work, cost visibility, confirmation, and audit requirements must be explicit rather than relying on creator-only access.
- Shared Collection configuration needs a visible stale-edit recovery path; automatic field merging is not implied by optimistic concurrency.
- Conflict recovery shows the submitted and current versions, reloads the current version, and lets the user reapply intended changes. It does not offer force overwrite as the ordinary recovery path.
- Raw cron, Sensor, Subscription, Prefect deployment, and container URL concepts do not appear in ordinary Collection workflows.
- Existing hardcoded localhost console links in the application header must be removed; administrator links come only from explicit protected configuration.
