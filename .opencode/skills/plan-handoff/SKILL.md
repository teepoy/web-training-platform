---
name: plan-handoff
description: Execute a multi-step plan autonomously after waiting for a clean git worktree. Defers all questions to the very end.
compatibility: opencode
metadata:
  audience: contributors
  workflow: plan-execution
---

## What I do

Accept a plan (inline or from `.sisyphus/plans/<name>.md`) and execute every step to completion without pausing for user confirmation. Ambiguities are collected and presented in a single batch at the very end.

## When to load this skill

Load this skill when:

- You are handed a plan to execute (inline in the prompt, or a path to a `.sisyphus/plans/*.md` file).
- The user says "execute the plan", "hand off", "run it", or similar.
- You are resuming a partially-completed plan after a session break.

## Pre-flight: wait for clean worktree

Before touching any code, ensure the git worktree has no non-Markdown uncommitted changes. This prevents merge conflicts with in-flight work from a prior session.

```bash
bash scripts/wait-for-code-clean.sh 5
```

- The script polls `git status --porcelain` every N seconds (default 5).
- It exits 0 when only `.md` files (or nothing) remain dirty.
- If the script is missing or fails, fall back to checking `git status --porcelain` manually and warn the user if non-Markdown changes exist.

Do NOT skip this step. If the worktree is not clean, wait.

## Plan loading

1. **File reference** -- If the prompt contains a path like `.sisyphus/plans/foo.md`, read that file as the plan.
2. **Inline plan** -- If the prompt contains a numbered/checkboxed task list, treat that as the plan.
3. **No plan found** -- Ask the user for a plan before proceeding. This is the ONE acceptable reason to ask a question before execution.

### Plan format (for authors)

Large-scale plans should be written to `.sisyphus/plans/<slug>.md` using this structure:

```markdown
# <Feature Name> Plan

**Goal**: One-sentence summary of what this plan achieves.
**Created:** <date>
**Status:** PENDING | IN PROGRESS | DONE

---

## TODOs

- [ ] T0: <task description>
- [ ] T1: <task description>
- [ ] ...

---

## Verification

- [ ] V0: `make test` passes
- [ ] V1: <additional verification>

---

## Key Constraints

- <constraint relevant to implementation>
- ...
```

The `.sisyphus/` directory is gitignored -- plans are ephemeral working documents. The code changes are the durable output.

## Execution rules

These rules are non-negotiable during plan execution.

### 1. Do NOT ask the user mid-execution

- If a step is ambiguous, pick the most reasonable default, document your choice as a comment or in the deferred-questions list, and continue.
- If a step fails (test failure, missing dependency, etc.), attempt recovery up to two times before adding it to the deferred-questions list and moving on to the next independent step.

### 2. Track every step with TodoWrite

- Before starting, create a TodoWrite list mirroring the plan steps.
- Mark each step `in_progress` when you start it.
- Mark each step `completed` immediately when done -- do not batch completions.
- Only one step should be `in_progress` at a time.

### 3. Follow the plan order unless steps are independent

- Execute steps sequentially by default.
- If the plan has an explicit dependency graph or marks steps as parallelizable, respect that.
- Do not skip steps unless they are explicitly marked as optional.

### 4. Update the plan file as you go

If executing from a `.sisyphus/plans/*.md` file, update the checkboxes in that file as you complete each step (`- [ ]` to `- [x]`). This provides crash-recovery state if the session is interrupted.

### 5. Run verification after all steps

- Run `make test` after all implementation steps are done.
- If the plan has a `## Verification` section, execute every item in it.
- Fix any failures before moving to the deferred-questions phase.

## Post-flight: deferred questions

After all steps are complete (or blocked), present a single consolidated block:

```
## Deferred Questions

1. [T3] Chose X over Y because <reason>. Confirm or override?
2. [T7] Step failed after 2 retries: <error summary>. How to proceed?
3. ...
```

If there are no deferred questions, say so explicitly and summarize what was done.

## Commit reminder

After execution is complete and tests pass, remind the user:

> All plan steps are complete and tests pass. Ready to commit when you are.

Do not commit automatically -- wait for the user to request it.
