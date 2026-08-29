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

| Goal                                                                                | Status      | Latest completed slice                                             | Next milestone                                                  |
| ----------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------ | --------------------------------------------------------------- |
| [Legacy configuration and code cleanup](legacy-configuration-and-code-cleanup.md)   | In progress | API configuration ownership and Make target consistency            | Continue the subsystem inventory and unnecessary-prefix cleanup |
| [Mock, seed, and demo package separation](mock-seed-code-package-separation.md)     | In progress | Simulator API owns SC rows/objects; test adapters are isolated     | Review web demo providers and development-only routes           |
| [Visual reuse and resource parity](visual-component-reuse-and-resource-parity.md)   | In progress | Removed the duplicate Dataset list surface                         | Share model search and standardize reusable table filters       |
| [Internationalization](internationalization-and-localization.md)                    | In progress | Localized navigation, authentication, settings, and shell surfaces | Migrate shared feedback and core resource/job workflows         |
| [Stateful upstream simulator](stateful-upstream-simulator-and-source-automation.md) | In progress | Named API scenario publishes PostgreSQL rows and MinIO objects     | Add five-minute internal Collection discovery                   |
| [SC identity-only materialization](sc-sample-identity-only-materialization.md)      | In progress | Identity-only writes and latest-source reads across core SC flows  | Verify generic sparse export and broad/E2E behavior             |

The Prefect GPU worker release task is tracked separately in
`prefect-gpu-worker-release-activation.md`; it is not one of these six
modernization goals.
