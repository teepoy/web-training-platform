# Modernization Goal Tracker

This directory tracks the modernization goals as multi-stage outcomes. A
completed intermediate slice is evidence of progress, not completion of the
parent goal. A goal becomes **Complete** only when its document's acceptance
criteria are satisfied.

## Status Meaning

- **Planned**: decisions and scope are recorded; implementation has not begun.
- **In progress**: at least one implementation or prerequisite slice is done,
  but acceptance criteria remain open.
- **Blocked**: a named external decision or dependency prevents the next slice.
- **Complete**: all acceptance criteria are verified.

## Current Goals

| Goal                                                                                | Status      | Latest completed slice                                               | Next milestone                                                    |
| ----------------------------------------------------------------------------------- | ----------- | -------------------------------------------------------------------- | ----------------------------------------------------------------- |
| [Legacy configuration and code cleanup](legacy-configuration-and-code-cleanup.md)   | In progress | API configuration ownership and Make target consistency              | Continue the subsystem inventory and unnecessary-prefix cleanup   |
| [Mock, seed, and demo package separation](mock-seed-code-package-separation.md)     | In progress | Settings scaffold removal and SC artifact generator relocation       | Remove mock implementations from production package paths         |
| [Visual reuse and resource parity](visual-component-reuse-and-resource-parity.md)   | In progress | Removed the duplicate Dataset list surface                           | Share model search and standardize reusable table filters         |
| [Internationalization](internationalization-and-localization.md)                    | In progress | Installed browser locale persistence and UI-library locale providers | Migrate global navigation, authentication, and settings copy      |
| [Stateful upstream simulator](stateful-upstream-simulator-and-source-automation.md) | In progress | PostgreSQL simulator, authenticated control API/CLI, and dev Compose | Expose published rows through gRPC/Flight and freshness transport |
| [SC identity-only materialization](sc-sample-identity-only-materialization.md)      | Planned     | Contract and migration design recorded                               | Implement the bulk live-source resolution boundary                |

The Prefect GPU worker release task is tracked separately in
`prefect-gpu-worker-release-activation.md`; it is not one of these six
modernization goals.
