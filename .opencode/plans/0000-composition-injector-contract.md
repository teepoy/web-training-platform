# 0000: Composition / Injector Contract

**Status**: draft
**Date**: 2026-06-18
**Blocks**: `0001-runtime-services-data-plane-refactor.md`

## Decision

Before the large storage/materializer/trainer/predictor refactor, establish API composition rules around the `injector` library and interface-only cross-module dependencies.

The normative contract lives at:

`docs/architecture/composition-contract.md`

## Why This Comes First

The following refactor steps move module boundaries. If they happen before composition rules are fixed, old concrete service coupling will be moved into new packages and become harder to unwind.

This step should happen first because it defines:

- how modules expose public local ports,
- how cross-module dependencies are injected,
- which concrete classes remain private to an owning module,
- how tests override dependencies,
- how root runtime services stay decoupled from API internals.

## Required Outcomes

- `apps/api` has one API composition root based on `injector`.
- Cross-module dependencies use Protocol interfaces, not concrete service classes.
- Route dependencies resolve interfaces from composition and keep handlers thin.
- Runtime services do not import API internals.

## Follow-Up Plans

After this contract is accepted, apply it while executing:

1. `0001-runtime-services-data-plane-refactor.md`
