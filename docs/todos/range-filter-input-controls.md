# TODO: Improve Numeric and Date Range Filter Controls

## Progress

- **Overall status:** Complete for the currently supported typed transports.
- **Current behavior:** SC numeric filters use the shared synchronized Slider
  and exact inputs. The shared filter layer also has an explicit browser-time-zone
  DateTime Range Picker contract that preserves its supplied interval endpoints.
- **Explicit boundary:** SC does not expose a date/time condition transport:
  `inspection_time` is currently a UTF-8/string field and SC conditions support
  only set and numeric `inRange` filters. Wiring the picker to that field would
  require an API field type and interval contract; timestamps are not coerced to
  numeric epochs in the frontend.

## Goal

Make range filters faster to operate while preserving precise, predictable
values:

- numeric ranges use a two-handle Slider synchronized with explicit minimum and
  maximum number inputs;
- date/time ranges use a DateTime Range Picker instead of free-form or numeric
  controls;
- both controls reuse the existing shared filter popover, clear/cancel/apply,
  loading, unavailable-range, validation, and accessibility behavior.

## Required Decisions

### Numeric ranges

- Slider bounds come from the server-provided observed range. Do not invent
  bounds when range statistics are unavailable.
- Keep exact number inputs beside the Slider. The Slider is a convenient
  controller, not a loss of precision or the only input method.
- Field metadata must define or derive an explicit step and display precision;
  do not assume all numeric fields are integers.
- Slider and inputs update one draft range and apply atomically. Partial,
  inverted, non-finite, and out-of-domain ranges remain invalid.

### Date/time ranges

- Date and timestamp field descriptors select a DateTime Range Picker rather
  than the numeric Slider.
- Display uses the active browser locale. Time-zone interpretation remains an
  explicit product/data contract and must not be inferred from locale.
- Transport values use the existing API field type and interval semantics. If
  a surface uses UTC `[start, end)`, the picker must preserve that contract
  rather than silently changing the end boundary.
- Clearing either range clears the complete draft condition.

## Initial Ownership

- Extend the shared table-filter layer beginning with
  `apps/web/src/shared/components/table-filter/RangeFilterMenu.vue`.
- Keep SC field descriptors, range-statistic loading, and condition mapping in
  the SC feature. Do not move SC query semantics into the shared visual
  component.
- Reuse the resulting numeric/date controls from other resource tables only
  when they expose the same typed range contract.

## Acceptance Criteria

- Numeric fields render synchronized Slider and exact min/max inputs.
- Date/time fields render a localized DateTime Range Picker.
- Loading, missing bounds, clear, cancel, apply, keyboard operation, and invalid
  range states have focused component tests.
- Existing server filter payloads and interval semantics remain unchanged.
- Representative numeric and date/time states are rendered for visual review.
- `make lint`, `make test-web`, and `make build-web` pass.

## Delivered

- One shared typed range descriptor chooses the numeric or date/time control.
- SC descriptors derive numeric Slider granularity from Arrow/format metadata.
- Both the global-filter builder and virtual sample table query observed bounds
  and preserve the existing exact numeric `inRange` payload.
- Loading, unavailable bounds, clear/cancel, keyboard support, precise values,
  invalid ranges, and the half-open date/time example have focused unit tests.
- Storybook renders numeric, date/time, and unavailable-bound states for visual
  review.

## Verification

Verification results are recorded with the implementation handoff. The direct
frontend binaries may be used when a concurrent workspace dependency edit makes
the package manager request an interactive reinstall; this does not change the
commands or product artifacts under test.
