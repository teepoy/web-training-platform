# ADR 0002: Production management surfaces

**Status:** Accepted (2026-08-15)

## Context

Label Studio, Prefect UI, and MinIO Console are all browser-accessible services, but they serve different audiences. Treating them as equivalent global navigation entries exposes execution and storage internals to ordinary users. Conversely, treating Label Studio as an operator-only console would remove a supported human-labeling workflow from datasets that rely on it.

The production Compose manifests intentionally publish no host ports. Deployment operators decide which services receive protected external routes on the shared production network.

## Decision

- Label Studio is a product work surface. It is launched contextually from a Dataset only when that dataset's capabilities include Label Studio annotation.
- Label Studio is not a standalone global management entry for ordinary users.
- Prefect UI and MinIO Console are operator consoles. They do not appear in ordinary-user navigation.
- If a Dataset supports Label Studio but the required external URL is not configured, its contextual action remains visible but disabled and explains that an administrator must configure the service address.
- An administrator-only platform page shows Prefect UI and MinIO Console configuration status and provides links when their protected external URLs are explicitly configured.
- Production access to any of these services requires an explicitly configured, TLS-protected and authenticated route or a private operator access path. The supplied production Compose manifests continue to publish no host ports.
- Direct MinIO API access remains a data-plane concern and is not implied by providing operator access to MinIO Console.

## Consequences

- Dataset capability and storage-mode checks determine whether the Label Studio action is shown; the frontend must not infer support from a hardcoded dataset type.
- Deployment documentation must distinguish a user-facing Label Studio route from operator-only Prefect and MinIO routes.
- Prefect and MinIO links must not be added to the general sidebar or dataset workflow UI.
- The administrator page must never synthesize localhost or container-internal console URLs. An unconfigured console is shown as unconfigured rather than as a broken link.
- Missing production routes cannot fall back to localhost or container-internal URLs.
