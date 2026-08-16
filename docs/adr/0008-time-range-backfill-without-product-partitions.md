# ADR 0008: Time-range Backfill without product Partitions

**Status:** Accepted (2026-08-15)

## Context

Enabling a membership rule only processes newly observed Source records. Users still need an explicit way to import historical records that match a chosen rule version and time range.

Some DAG runners model backfill through durable asset partitions or scheduled data intervals. In this platform, the durable processing identity is already the provider-owned Source record plus membership rule, Import profile, and Discovery receipt. A historical time range selects records to discover; it does not by itself define a long-lived data asset partition.

Exposing Partition, logical date, or DAG-run concepts would increase the learning burden for ordinary Collection users without adding business identity.

## Decision

- The product exposes `Import historical data` / `补录历史数据` as a separate Backfill operation. It does not expose a general Partition concept.
- A Source provider that supports Backfill declares the business timestamp field used for range queries.
- The user supplies an IANA timezone and an explicit start and end. The API normalizes the request to a UTC half-open interval `[start, end)`.
- A Backfill pins the membership rule version, Source connector, and Import profile present when it starts. Later rule edits do not change the running Backfill.
- Preflight shows an as-of timestamp, a provider-produced match-count estimate, and representative records rather than exhaustively materializing the requested range. Submission is blocked if the provider cannot resolve an estimate; the completed run records actual scanned, matched, suppressed, skipped, succeeded, and failed counts.
- Backfill uses an independent cursor and never advances or rewinds the live-discovery watermark.
- Backfill and live discovery may run concurrently. Collection admission is serialized and uses Discovery receipts plus Collection-level Source identity deduplication.
- A Backfill may split work into internal execution windows, but it publishes at most one final Snapshot containing all successfully admitted members. Individual Source record failures produce a visible partial result and remain retryable.
- The final Snapshot resolves the latest merged Collection head, including valid admissions made concurrently by live discovery. Backfill provenance separately identifies which members were admitted by that Backfill.

## Consequences

- The ordinary-user flow is rule summary, time-range selection, match preview, Backfill submission, and progress/result review; internal execution windows are not presented as partitions.
- Source providers without a declared historical business-time field cannot offer time-range Backfill and must expose that missing capability explicitly.
- Backfill execution limits and window sizes must be explicit operator or Import-profile configuration; they cannot be hidden runtime defaults.
- Receipt and membership provenance allow Backfill to resume or coexist with live discovery without duplicate Dataset creation.
- A long Backfill does not create a Snapshot per internal batch, keeping Snapshot history aligned with business publication rather than resource-control mechanics.
