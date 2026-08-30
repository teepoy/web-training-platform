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

| Goal                                                                                                                  | Status   | Latest completed slice                                                                   | Next milestone |
| --------------------------------------------------------------------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------- | -------------- |
| [Legacy configuration and code cleanup](legacy-configuration-and-code-cleanup.md)                                     | Complete | Canonical configuration ownership and retired UI packages verified                       | —              |
| [Mock, seed, and demo package separation](mock-seed-code-package-separation.md)                                       | Complete | Dev/test/simulator code has explicit package and composition owners                      | —              |
| [Visual reuse and resource parity](visual-component-reuse-and-resource-parity.md)                                     | Complete | Shared list/model/filter/target contracts and names are verified                         | —              |
| [Internationalization](internationalization-and-localization.md)                                                      | Complete | English/Chinese production UI and literal enforcement verified                           | —              |
| [Stateful upstream simulator](stateful-upstream-simulator-and-source-automation.md)                                   | Complete | Stateful API/CLI simulator and five-minute discovery poll verified                       | —              |
| [SC identity-only materialization](sc-sample-identity-only-materialization.md)                                        | Complete | Identity-only storage and latest-source resolution verified                              | —              |
| [SC selection and data pipeline efficiency](sc-selection-and-data-pipeline-efficiency.md)                             | Complete | Multi-label selection, linear identity pipeline, and gzip query bodies verified          | —              |
| [Partitioned SC automation and multi-inspection classify](sc-partitioned-automation-and-multi-inspection-classify.md) | Complete | Exact partition exclusivity, Revision member selection, and active-map behavior verified | —              |
| [Annotation, Dataset, and Model import/export](annotation-dataset-model-import-export.md)                             | Complete | Registered, bounded transfer flows and round trips verified                              | —              |
| [Upstream-mock seed ownership](upstream-mock-seed-ownership.md)                                                       | Complete | Dev-only superadmin bootstrap and live login verified                                    | —              |
| [Dataset compatibility and transfer UX hardening](dataset-compatibility-and-transfer-ux.md)                           | Complete | Storage-mode compatibility, transfer UX, and portable Models verified                    | —              |
| [SC Collection Revision and class taxonomy](sc-collection-revision-and-class-taxonomy.md)                             | Complete | Revision-only current-data semantics, class mapping, and regression coverage verified    | —              |

The Prefect GPU worker release task is tracked separately in
`prefect-gpu-worker-release-activation.md`; it is not part of the modernization
goal table above.
