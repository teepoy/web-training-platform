# Legacy Playwright Scenarios

These specs document pre-redesign Preview, Classify, sample-browser, export,
and wafer-map behavior. They remain below the single `e2e/` root for reference,
but `playwright.config.ts` collects only `e2e/specs/`, so this directory is not
part of the active mock or live suites.

Do not re-enable a legacy spec by only changing its tag or timeout. Migrate its
selectors, routes, handlers, and assertions to the current UI contract first,
move it into `e2e/specs/<feature>/`, and assign exactly one of `@mock` or
`@live`.
