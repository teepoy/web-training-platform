# TODO: Add Internationalization and Localization

## Progress

- **Overall status:** Complete.
- **Completed outcome:** English and Simplified Chinese now cover the agreed
  production frontend surface, including shared widgets, descriptor-driven
  transfer flows, SC discovery/classification/map/sampling controls, visible
  copy, and accessibility labels. Locale selection persists per browser and
  drives the application, Naive UI, VXE UI/Table, shared formatting, and
  document language.
- **Enforcement:** catalog tests require key and interpolation parity; the lint
  workflow rejects untranslated static copy, labels, tabs, descriptions, and
  accessibility attributes in the dense SC/shared-component scope. The SC
  handbook is the documented English-fallback exception.
- **Verification:** `make lint`, all 516 web unit tests, the production web
  build, the explicit English regression suite, and the English/Chinese locale
  persistence smoke pass.

This document tracks the incremental internationalization of the product UI.
The first phase covers
frontend-visible strings and does not change backend error or generated message
contracts.

## Current State

- Vue I18n is installed during application bootstrap with English and
  Simplified Chinese catalogs.
- The selected locale is persisted per browser and synchronizes the document,
  Naive UI, VXE UI, and VXE Table locale.
- Global navigation and user-menu copy is translated, and language controls are
  available both before and after sign-in.
- Production copy and presentation metadata resolve through locale catalogs;
  stable IDs, protocol values, file formats, and user-entered data remain
  untranslated.
- Shared helpers own locale-aware dates, times, numbers, percentages, file
  sizes, and relative time. The existing browser/business time-zone behavior is
  intentionally independent of locale.
- The API primarily returns English `HTTPException.detail` strings. The web
  transport maps a few HTTP statuses to separate hard-coded English messages,
  but there is no general machine-readable error contract for localization.

## Resolved Decisions

- Initial locales are English (`en`) and Simplified Chinese (`zh-CN`).
- English is the source and fallback locale.
- Locale is a per-browser preference stored locally. Precedence is stored
  browser choice, supported browser language, then English fallback.
- The application provides a visible language selector; changing it updates
  application copy, component-library copy, formatting locale, and `<html
lang>` without requiring sign-in.
- The first phase covers frontend-visible strings and accessibility text only.
  Backend error prose, generated email/task text, runtime logs, and API error
  contract changes are out of scope.
- During extraction, lightly normalize inconsistent capitalization,
  punctuation, terminology, and duplicated wording. Do not combine i18n with a
  broad product-copy rewrite. English keys remain the semantic reference and a
  reviewed glossary governs recurring domain terms.
- Neither initial locale requires right-to-left layout support.
- Time zone remains independent of language. Locale changes formatting and
  language only; existing browser/business time-zone behavior is preserved
  until a separate time-zone feature is approved.
- The production interface and accessibility text ship in both initial locales.
  The SC handbook may remain English initially and uses explicit English
  fallback when a Chinese translation is unavailable.
- Existing routes, API values, workflows, permissions, and stored preferences
  remain backward-compatible. This frontend-only migration requires no data
  backfill.

## Candidate Inventory

### P0: Application-level i18n infrastructure is absent

Files:

- `apps/web/package.json`
- `apps/web/src/app/main.ts`
- `apps/web/src/app/App.vue`
- `apps/web/index.html`
- `apps/web/src/features/auth/application/ui.ts`

Required foundation:

- Install one Vue-compatible translation runtime and create the application
  i18n instance during bootstrap.
- Add a typed locale registry with an explicit source locale, supported locale
  list, fallback locale, and lazy-loaded message catalogs.
- Keep application infrastructure in an app/shared i18n package; keep
  feature-specific messages near their owning feature or in feature-scoped
  namespaces rather than one unowned global file.
- Store and hydrate the selected locale according to the agreed precedence.
- Update `document.documentElement.lang` whenever the locale changes and set
  the initial value before or during application bootstrap.
- Localize the document title and define whether route-specific document titles
  are required.
- Expose a language selector in an agreed location, most likely the user menu or
  settings, including on authentication pages if locale selection must work
  before sign-in.

Completed: the locale registry, persistence precedence, provider installation,
document title/`lang` synchronization, and pre/post-auth language selectors are
implemented. The initial catalogs contain the application shell namespace;
feature catalogs and remaining visible strings stay as incremental work.

### P0: Component-library locale providers are not connected

Files:

- `apps/web/src/app/App.vue`
- `apps/web/src/app/main.ts`

The application uses Naive UI, VXE UI, and VXE Table. Theme configuration is
centralized, but component-library language, date-locale, pagination,
validation, empty-state, and table messages are not tied to an application
locale.

Proposed direction:

- Map each supported application locale to the corresponding Naive UI locale
  and date locale.
- Change the VXE UI/Table language when the application locale changes.
- Verify all used component-library locales exist; document any fallback or
  local override for missing vendor strings.
- Add a provider-level test so application text and third-party component text
  cannot drift into different languages.

Completed: Naive UI common/date locales and VXE UI/Table catalogs now follow the
application locale. Locale tests cover normalization, precedence, persistence,
and document synchronization; full type-check/build verification covers the
provider bindings.

### P0: Global navigation, authentication, and settings are hard-coded

Files and features:

- `apps/web/src/app/App.vue`
  - Product name, sidebar menu labels, user menu labels, local-user fallback,
    and accessible labels.
- `apps/web/src/app/layouts/AdminLayout.vue`
- `apps/web/src/app/layouts/SettingsLayout.vue`
- `apps/web/src/features/auth/presentation/pages/LoginView.vue`
- `apps/web/src/features/auth/presentation/pages/RegisterView.vue`
- `apps/web/src/features/auth/presentation/pages/OAuthRegisterView.vue`
- `apps/web/src/features/auth/presentation/pages/OAuthCallbackView.vue`
- `apps/web/src/features/settings/presentation/pages/SettingsView.vue`
- `apps/web/src/features/admin/presentation/pages/AdminInfrastructureView.vue`
- `apps/web/src/features/dashboard/presentation/pages/DashboardView.vue`

These are the first surfaces a user encounters and contain hard-coded headings,
buttons, placeholders, validation text, table headers, states, errors, dialogs,
and notifications. They should form the first end-to-end migration slice after
the foundation is in place.

### P0: Shared feedback and formatting utilities are English-only or scattered

Files:

- `apps/web/src/shared/api/client.ts`
- `apps/web/src/shared/components/creator-scope-select/CreatorScopeSelect.vue`
- `apps/web/src/shared/components/bulk-selection-toolbar/BulkSelectionToolbar.vue`
- `apps/web/src/shared/components/agent-chat-drawer/AgentChatDrawer.vue`
- `apps/web/src/shared/components/browser-sidebar/BrowserSidebar.vue`
- `apps/web/src/shared/components/sample-detail-drawer/SampleDetailDrawer.vue`
- `apps/web/src/shared/components/task-insight-modal/TaskInsightModal.vue`
- `apps/web/src/shared/components/run-log-viewer/RunLogViewer.vue`
- `apps/web/src/shared/components/preview-item-drawer/PreviewItemDrawer.vue`
- `apps/web/src/shared/components/datasets/dataset-page-shell/DatasetPageShell.vue`
- `apps/web/src/shared/datasets/surface.ts`
- `apps/web/src/features/datasets/application/surface.ts`

`toUserMessage()` currently returns hard-coded English for timeout, network,
authentication, authorization, not-found, conflict, validation, and cancellation
cases. Shared components also embed reusable button, accessibility, status,
empty-state, and error text. Date and number formatting is repeated through
direct `toLocale*` and `Intl` calls.

Proposed direction:

- Make user-message resolution return translation keys plus parameters, or
  accept an i18n formatter at the presentation boundary; do not import Vue
  presentation state into the low-level transport client.
- Add shared locale-aware date, time, relative-time, number, percent, file-size,
  and pluralization helpers.
- Require an explicit time-zone policy in date/time helpers.
- Move reusable component copy into shared namespaces while leaving
  feature-specific wording with the owning feature.
- Use interpolation and plural rules for counts instead of manual string
  concatenation and English singular/plural suffixes.

### P0: Core resource and job workflows contain extensive embedded English

Files and features:

- `apps/web/src/features/library/presentation/pages/LibraryWorkspaceView.vue`
- `apps/web/src/features/datasets/presentation/pages/DatasetListView.vue`
- `apps/web/src/features/datasets/presentation/pages/DatasetDetailView.vue`
- `apps/web/src/features/datasets/presentation/pages/DatasetViewPage.vue`
- `apps/web/src/features/datasets/presentation/components/ManualImporter.vue`
- `apps/web/src/features/datasets/presentation/components/ManualDatasetImporter.vue`
- `apps/web/src/features/datasets/presentation/components/ParquetImporter.vue`
- `apps/web/src/features/datasets/presentation/components/ParquetExportPlugin.vue`
- `apps/web/src/features/datasets/presentation/components/PersistExportPlugin.vue`
- `apps/web/src/features/datasets/presentation/components/PreviewExportPlugin.vue`
- `apps/web/src/features/datasets/presentation/components/DatasetSparseSummary.vue`
- `apps/web/src/features/dataset-collections/presentation/pages/DatasetCollectionListView.vue`
- `apps/web/src/features/dataset-collections/presentation/pages/DatasetCollectionDetailView.vue`
- `apps/web/src/features/dataset-collections/presentation/components/CollectionSnapshotUpdateAlert.vue`
- `apps/web/src/features/models/presentation/pages/ModelsView.vue`
- `apps/web/src/features/models/presentation/components/RemoteModelPicker.vue`
- `apps/web/src/features/training/presentation/pages/TrainingJobsView.vue`
- `apps/web/src/features/training/presentation/pages/JobDetailView.vue`
- `apps/web/src/features/prediction/presentation/pages/PredictionJobsView.vue`
- `apps/web/src/features/task_tracker/presentation/pages/TaskExplorerView.vue`
- `apps/web/src/features/automations/presentation/pages/AutomationsView.vue`
- `apps/web/src/features/schedules/presentation/pages/SchedulesView.vue`
- `apps/web/src/features/schedules/presentation/pages/ScheduleDetailView.vue`

The affected text includes page and card titles, filter labels, placeholders,
table columns, status labels, empty states, form validation, confirmations,
success/error messages, action names, and count summaries. Some status labels
are generated by capitalizing or replacing underscores in API values; those
must instead map stable domain values to translation keys.

Proposed direction:

- Migrate by complete user workflow rather than by string type, so one screen
  does not mix languages.
- Define feature namespaces and reuse shared keys only for genuinely identical
  concepts such as Save, Cancel, Delete, Retry, Search, and Clear filters.
- Keep resource names, user-entered values, IDs, trainer identifiers, and model
  metadata unchanged.
- Use localized domain-label maps for statuses, source types, policies, actions,
  and task kinds; never use translated labels as API values or business keys.

### P1: The SC workspace has dense UI copy and long-form documentation

Files and features:

- `apps/web/src/features/sc/presentation/pages/PreviewPage.vue`
- `apps/web/src/features/sc/presentation/pages/InspectionPage.vue`
- `apps/web/src/features/sc/presentation/pages/ReclassifyPage.vue`
- `apps/web/src/features/sc/presentation/pages/HandbookPage.vue`
- `apps/web/src/features/sc/application/usePreviewPage.ts`
- `apps/web/src/features/sc/application/useReclassifyPage.ts`
- `apps/web/src/features/sc/presentation/components/ScSummaryTab.vue`
- `apps/web/src/features/sc/presentation/components/ScSampleTableTanStack.vue`
- `apps/web/src/features/sc/presentation/components/ScBlinkVirtualTable.vue`
- `apps/web/src/features/sc/presentation/components/ScMapPanelBinned.vue`
- `apps/web/src/features/sc/presentation/components/ScGlobalFilterQueryBuilder.vue`
- `apps/web/src/features/sc/presentation/components/ScDatasetGlobalFilterControl.vue`
- `apps/web/src/features/sc/presentation/components/ReviewSamplingModal.vue`
- `apps/web/src/features/sc/presentation/components/ScPredictionExportPlugin.vue`
- `apps/web/src/features/sc/presentation/components/ReclassifyTaskProgressModal.vue`
- `apps/web/src/features/sc/presentation/components/ReclassifyAnnotationSidebar.vue`
- `apps/web/src/features/sc/presentation/components/ScGalleryColorSettings.vue`
- `apps/web/src/features/sc/presentation/components/ScLegend.vue`
- `apps/web/src/features/sc/domain/missingFilterValue.ts`
- `apps/web/src/features/sc/presentation/registrations/predictionExport.ts`
- `apps/web/src/features/sc/handbook/sc-guide.md`

This area includes table and map accessibility labels, filter-builder terms,
selection counts, sampling rules, progress stages, export guidance, error and
success messages, and dynamically constructed labels. The handbook is loaded as
one English Markdown file and its headings generate the table of contents.

Proposed direction:

- Treat SC terminology as a feature-owned glossary so the same domain term is
  translated consistently across tables, maps, filters, sampling, and export.
- Localize accessibility text at the same time as visible text.
- Store long-form handbook content by locale and load the selected locale's
  Markdown lazily; keep stable explicit heading IDs if cross-locale deep links
  must remain valid.
- Keep semiconductor codes, field identifiers, file formats, and externally
  defined protocol terms unchanged unless the glossary explicitly supplies a
  display translation.

### P1: Descriptor and plugin metadata has no localization contract

Files:

- `apps/web/src/app/registrations.ts`
- `apps/web/src/features/sc/presentation/registrations/predictionExport.ts`
- `apps/web/src/shared/widgets/sdk/`
- `apps/web/src/shared/widgets/sdk/templates/ImporterIndexTemplate.ts`

Registered exporters, importers, widgets, preview launchers, and similar
extensions expose static English labels and descriptions. If descriptors are
loaded before Vue components, they cannot depend casually on component-scoped
translation hooks.

Proposed direction:

- Extend descriptor display metadata to use stable translation keys or a
  locale-aware label resolver while preserving stable IDs for registration and
  persistence.
- Define how external plugins provide message catalogs and what happens when a
  plugin omits the active locale.
- Keep extension registration import-safe and avoid requiring a mounted Vue
  component to resolve labels.

### Deferred: API errors are English prose rather than a localization contract

Representative files and areas:

- `apps/web/src/shared/api/client.ts`
- `apps/api/app/modules/auth/port/http/router.py`
- `apps/api/app/modules/auth/port/http/deps.py`
- `apps/api/app/modules/datasets/port/http/router.py`
- `apps/api/app/modules/dataset_collections/port/http/router.py`
- `apps/api/app/modules/models/port/http/router.py`
- `apps/api/app/modules/training/port/http/router.py`
- `apps/api/app/modules/prediction/port/http/router.py`
- `apps/api/app/modules/jobs/task_tracker/port/http/router.py`
- `apps/api/app/modules/jobs/schedules/app/services/scheduler.py`
- `apps/api/app/modules/sc/port/http/router.py`
- `apps/api/app/shared/infrastructure/prefect/client.py`

Many endpoints return English `detail` strings or raw exception text. Some
domain errors already carry codes, but this is not a consistent API-wide
contract. Translating text inside the API would mix presentation policy into the
control plane and still leave web clients unable to interpolate consistently.

This is not part of the first frontend-only i18n phase. A later API-contract
project may use this proposed direction:

- Define a structured error response containing a stable error code, safe
  interpolation parameters, optional field/path information, request ID, and a
  non-localized diagnostic detail where appropriate.
- Localize known error codes in the web application and use a localized generic
  fallback for unknown codes.
- Never expose raw internal exception details merely to improve translated UI.
- Preserve machine-readable codes in logs, events, generated OpenAPI clients,
  and tests.
- Treat API error-contract changes as OpenAPI changes: update source schemas,
  run generation, update the web client, and verify contract sync.
- Do not add `Accept-Language` or server-side translation unless another API
  consumer has a concrete requirement for localized server prose.

### P2: Tests are coupled to English text and do not exercise locale switching

Files and features:

- `apps/web/e2e/specs/auth/`
- `apps/web/e2e/specs/datasets/`
- `apps/web/e2e/specs/automations/`
- `apps/web/e2e/specs/sc/`
- `apps/web/e2e/legacy/`
- Component tests and stories throughout `apps/web/src`.

Many E2E locators use English roles, labels, placeholders, headings, and exact
text. Accessible-name assertions remain valuable, but the suite needs an
explicit locale strategy so adding a second language does not make the default
suite ambiguous or brittle.

Proposed direction:

- Keep the main regression suite pinned to an explicit source locale.
- Add a smaller locale-switching suite covering persistence, application and
  vendor component text, document language, formatting, and fallback behavior.
- Prefer stable test IDs for workflow mechanics that are unrelated to copy;
  retain accessible-name assertions where the translated accessible text is the
  behavior under test.
- Add missing-key, duplicate-key, interpolation-parameter, and unused-key checks
  to lint or build verification.
- Fail CI when source UI code adds unapproved literal user-facing text outside
  documented exceptions.

## Explicit Non-Candidates

- User-entered names, descriptions, labels, prompts, and annotation content are
  data and must not be translated automatically.
- Dataset IDs, sample IDs, model/trainer identifiers, status codes, field names,
  file formats, URI schemes, and API enum values remain stable machine values;
  only their display labels are localized.
- Runtime logs, Prefect logs, stack traces, request IDs, and low-level diagnostic
  details should remain source-language technical records unless a separate
  support requirement is approved.
- Generated OpenAPI/protobuf code should not be edited manually. Localized
  labels belong in source schemas or the web presentation layer.
- Storybook-only example data and development sandbox text are lower priority;
  production UI and shared components should migrate first.
- Locale is not a replacement for time-zone configuration. Date formatting and
  time-zone selection must remain separate, explicit concerns.

## Proposed Execution Order

1. Add the typed i18n bootstrap, lazy catalogs, locale store, document language,
   and component-library locale adapters.
2. Add shared formatting/pluralization helpers and a machine-readable web error
   message resolver.
3. Migrate application chrome, authentication, settings, and one resource list
   as the first complete vertical slice.
4. Migrate shared components, then dataset/collection/model/job workflows by
   complete screen or workflow.
5. Migrate the SC workspace using a reviewed domain glossary, followed by
   locale-specific handbook content.
6. Add descriptor/plugin localization and document the extension contract.
7. Update tests, stories, and static checks; then remove remaining unapproved
   hard-coded production UI strings.

## Acceptance Criteria

- The application declares an explicit active locale and fallback locale.
- Users can select a supported locale, the choice follows the agreed persistence
  policy, and `<html lang>` updates correctly.
- Application copy and Naive UI/VXE Table built-in copy use the same locale.
- At least two approved locales cover the agreed production surface, with no
  mixed-language screen except documented fallback content.
- Dates, times, numbers, percentages, file sizes, relative times, and plurals
  use shared locale-aware formatting with an explicit time-zone policy.
- Visible text and accessibility labels are localized together.
- Feature descriptors and plugin surfaces resolve localized labels without
  changing their stable IDs.
- Frontend-owned network, timeout, authentication, authorization, not-found,
  conflict, validation, and cancellation fallbacks are localized. Raw backend
  prose remains outside the first-phase contract and uses a safe localized
  fallback where the client cannot map it reliably.
- The selected E2E smoke flows pass in every supported locale, and the complete
  regression suite runs in an explicit source locale.
- Missing keys, invalid interpolation parameters, and unapproved literal UI
  strings fail automated checks.
- `make lint`, `make test-web`, and `make build-web` pass after each migration
  slice.

## Before Implementation

English/Simplified Chinese, browser-local persistence, frontend-only scope,
light copy normalization, independent time-zone behavior, and English handbook
fallback are approved. Split this work into backward-compatible vertical
feature migrations. A global mechanical replacement of English strings should
not be used because pluralization, interpolation, accessibility, and domain
terminology need deliberate keys and ownership.

Implementation is complete. Future frontend features must use the established
catalog, formatting helpers, localized descriptor metadata, and literal check;
backend error localization remains a separately scoped API-contract project.
