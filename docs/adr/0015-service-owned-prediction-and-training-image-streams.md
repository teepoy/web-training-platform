# ADR 0015: Service-owned Prediction and Training image streams

**Status:** Accepted (2026-08-21)

## Context

SC Training and Prediction previously launched a job-local Go resolver through a length-prefixed protobuf pipe, while browser display used the network image-parser service. That split isolated online display capacity, but duplicated source acquisition and cache behavior in worker images, made equipment-specific routing depend on entrypoint configuration, and prevented one service from optimizing ordered high-throughput image delivery. Prediction requires at least 3,000 two-image samples per second on a representative warm-cache workload; Training benefits mainly from a clear ownership boundary rather than the same optimization target.

## Decision

- Image resolution is owned by the image-parser service. Prediction, Training, and image-bearing Export use separate bidirectional gRPC streaming RPCs with explicit Inspection contexts, bounded request/result batches, backpressure, ordered sequence results, and separate metrics and resource budgets.
- Opening a context resolves `(inspection_time, wafer_key)` to `eqp_id` once. A code-owned exact registry selects an Equipment image entry composed from an Image artifact downloader and Image artifact parser; callers cannot select a format, source root, stager, or parser implementation.
- Display, Prediction, Training, and Export share one Cache Manager contract but use independent cache namespaces, capacity, TTL, concurrency, and metrics. Cache identity comes from the entry-provided source identity plus a reliable source revision. Object VersionId or ETag is preferred; reliable source mtime plus size is allowed for files, while directories require a provider generation, manifest revision, or reliable aggregate update time. Downloaded local mtime is eviction metadata, not source freshness.
- Cache misses use process-local singleflight plus an exclusive filesystem advisory lock. The lock holder rechecks the final target, streams into a sibling temporary location, validates and syncs it, then publishes with an atomic rename. Cache acquisition returns an explicit Artifact lease: parsers and indexes hold a shared lock while using the published path, and Janitor deletes only after it obtains the same entry's exclusive lock non-blockingly. Directory artifacts are measured recursively and evicted whole rather than file by file.
- Prediction and Training clients receive raw compressed image bytes and perform algorithm preprocessing themselves. Item corruption remains an item error; context source failures and transport failures remain visible at their owning boundary.
- One sequence identifies one sample and carries all requested image roles. The service may download and parse concurrently but returns externally strict sequence order through a bounded reorder buffer. Stream recovery is stateless and at-least-once: clients reopen contexts and resend from the first unacknowledged sequence. The service does not persist gRPC sessions.
- Contexts close explicitly, on stream cancellation, or after an idle timeout; long-running streams have no fixed total lifetime. An opening acknowledgement advertises batch, response-byte, and active-context limits. Image payloads are not recompressed by gRPC.
- One deployment initially serves all use cases. Per-use-case queues and semaphores feed a global weighted-fair limiter so Display retains latency capacity, Prediction receives the primary throughput allocation, and Training cannot starve.
- All job-local image-parser binaries, framed transports, subprocess adapters, binary configuration, and worker/API image copies are removed after both runtime consumers migrate. There is no compatibility fallback to the old path.

## Consequences

- The image-parser service becomes a required data-plane dependency for both Training and Prediction, so its availability, capacity isolation, deployment checks, and observability become part of ML job reliability.
- Display, Prediction, and Training may temporarily store duplicate source artifacts in exchange for predictable eviction and contention boundaries. A shared content-addressed store can be considered later without changing the RPC semantics.
- The first phase implements a semantically separate Training stream without prematurely copying Prediction-specific optimizations.
- The blocking performance gate uses 300,000 representative samples with two compressed images per sample and measures warm-cache service parsing through Python receipt. It must sustain at least 3,000 samples per second. Cold-cache source throughput and an additional decode/fake-predictor run are reported separately rather than folded into that gate.
