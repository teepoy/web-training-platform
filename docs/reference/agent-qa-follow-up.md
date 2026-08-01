# Agent QA Follow-up Register

Status: Open
Recorded: 2026-08-01
Owner area: Web app shell, Agent adapter, and POST-SSE transport

## Scope and evidence

The live Agent QA added in `apps/web/e2e/specs/agent/agent-chat.spec.ts`
creates a real dataset, opens the global Agent drawer from the dataset detail
route, sends a read-only prompt, and checks the `/api/v1/agent/chat` request.
It also records page errors and unexpected browser console errors.

The last dev-stack run exercised the explicit `503 LLM not configured` path.
That is a valid availability/error-path check, but it is not evidence that a
configured LLM can finish a real SSE response or produce a useful answer.

## Unfixed findings

| ID | Finding | Evidence / risk | Completion condition |
| --- | --- | --- | --- |
| AQA-001 | The Agent POM uses `.acd-*` CSS class selectors. | `apps/web/e2e/pages/agent/AgentChatPage.ts` conflicts with the repository rule requiring role, placeholder, or stable `data-testid` selectors. A visual refactor can break QA without changing behavior. | Add semantic roles/test IDs to `AgentChatDrawer.vue`, migrate the POM, and keep styling classes out of E2E selectors. |
| AQA-002 | Only the normal dataset-detail app-shell branch is covered. | `App.vue` mounts the drawer separately in the normal branch and the settings/admin branch. The latter can regress independently. | Add a cheap route-matrix check covering every non-auth app-shell branch that promises the global Agent entry. |
| AQA-003 | The configured-LLM success path is not currently proven by live QA. | The dev run accepted the explicit 503 path, so model invocation, streamed content, completion, and answer usefulness were not exercised. | Run the same spec in an acceptance profile with valid LLM configuration and require HTTP 200, `text/event-stream`, at least one response event, and `done`. |
| AQA-004 | Early consumer exit does not explicitly release the POST-SSE reader lock. | `parseSSEStream()` has no `finally` block that cancels or releases its `ReadableStreamDefaultReader`. Abort is wired, but iterator cancellation/consumer failure has no direct lifecycle assertion. | Define reader ownership, add cancellation/early-return unit coverage, and prove the reader is cancelled/released without leaving the Agent status in `streaming`. |
| AQA-005 | The current live test does not run in the normal PR-safe mock profile. | The only active Agent QA scenario is tagged `@live`; a shell or drawer regression can wait until a live environment is available. | Add a deterministic `@mock` contract test for drawer/context/error handling while retaining the live transport test. |

## Fixed but not fully verified

| ID | Change already made | Verified now | Remaining verification |
| --- | --- | --- | --- |
| AQA-101 | Re-enabled `AgentChatDrawer` in both non-auth `App.vue` layout branches. | The live dataset-detail route proves the normal branch renders and sends. | Exercise settings and admin routes; verify auth pages intentionally do not mount it. |
| AQA-102 | Disabled the ordinary request timeout for Agent and other completion SSE streams. | `src/shared/api/sse.spec.ts` proves `AbortSignal.timeout()` is not installed by the wrapper. | Hold a configured live Agent response beyond the former timeout and verify success, user abort, route leave, and component unmount cleanup. |
| AQA-103 | Added explicit missing-body handling for the Agent response stream. | Unit construction covers a readable SSE response. | Add a response-without-body/error-response case and assert a visible, actionable UI error. |
| AQA-104 | Added live assertions for dataset ID and current route context. | Dataset detail context is asserted exactly. | Cover context changes after in-app navigation and any selected-sample/filter context that Agent skills rely on. |

## Verification commands

Run the deterministic checks first:

```bash
make lint
pnpm --dir apps/web test:unit -- src/shared/api/sse.spec.ts \
  src/shared/components/agent-chat-drawer/AgentChatDrawer.spec.ts
pnpm --dir apps/web test:e2e --grep "Agent QA"
```

Then run the real backend path from a clean dev or acceptance stack:

```bash
pnpm --dir apps/web test:e2e:live --grep "Agent QA"
```

For configured-LLM acceptance, a `503` is a failure even though the ordinary
dev-stack check permits it. Record whether the run exercised `503` or `200`;
do not report the former as successful model-response coverage.
