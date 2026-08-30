# TODO: Prefect GPU Worker Release Activation

This document tracks deferred operational work for versioned Prefect GPU worker
release management. It is a proposal, not an active runtime contract.

### Problem

The host-side `default-gpu` Prefect worker runs from the current checkout and
does not fetch or install updates. Compose and production workers instead bake
application code and dependencies into an image, so changing source files does
not consistently update every runtime package. Updating a branch in place could
also change code underneath an active training or prediction run.

The implementation must define "latest" as the latest approved CI release,
identified by a full Git commit and immutable image digest. It must not make a
production worker follow a mutable branch or run `git pull` itself.

### Proposed Direction

Add a host-side release activator that consumes a CI-produced manifest containing
the commit, GPU worker image digest, creation time, and manifest schema version.
The activator should pre-fetch and validate the release, wait until the GPU pool
is idle, briefly stop new work from being claimed, atomically activate the new
release, and verify the new worker before restoring normal scheduling.

For a host-native development worker, use versioned checkouts and frozen virtual
environments under a runtime-owned release directory. Switch a `current`
symlink only after the new checkout and environment pass validation; never
modify the developer's working tree.

### Acceptance Criteria

- The desired release is a full commit plus immutable image digest, not a branch
  head or mutable tag.
- Only one update can run per GPU host at a time.
- Download and validation happen while the current worker remains available.
- An update with active GPU flow runs remains pending; it does not cancel them.
- Activation prevents the old worker from claiming new runs, rechecks that the
  pool is idle, and switches the release atomically.
- The new worker must publish a heartbeat containing its host and short commit,
  then pass a small GPU canary before activation succeeds.
- A failed heartbeat or canary restores the previous release automatically.
- Training and prediction jobs record the code commit, image digest, worker
  name, and Prefect deployment version used for execution.
- Admin infrastructure status exposes desired, active, previous, pending, and
  failed release states. Forced cancellation remains a separate restricted
  operation.
- Old releases are retained for rollback and removed only by an explicit
  retention policy.

### Prerequisite

Reconcile the current topology before implementation: the registered runtime
deployments still target the `default-gpu` Process work pool, while
`docs/architecture/task-tracker.md` describes GPU execution as delegated to a
separate HTTP GPU worker. The release activator must follow the selected
authoritative topology rather than supporting both implicitly.

### Later Evaluation

Evaluate moving GPU flow runs to Docker or Kubernetes work pools where a stable
Prefect worker launches one immutable runtime image per run. That model would
allow active runs to finish on their original digest while new runs immediately
use the newly activated digest, without updating the worker process itself.
