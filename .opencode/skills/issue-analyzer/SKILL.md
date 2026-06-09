---
name: issue-analyzer
description: Use when the user reports a bug, asks to analyze root cause, audit code for issues, diagnose a problem, or compare plan vs implementation. Produces a structured issue analysis under ./issues without changing production code.
compatibility: opencode
metadata:
  audience: contributors
  workflow: issue-analysis
---

# Issue Analyzer

Use this skill for bug reports, root-cause analysis, implementation-gap audits, and diagnostic writeups.

Do not use it for direct code fixes, feature implementation, or casual Q&A that does not need a persistent report.

## Rules

- **Strictly read-only**: do NOT modify any production code, config files, tests, or any file outside `./issues/`. This includes `useReclassifyPage.ts`, `router.py`, `.vue` components, and all other source files. The only allowed write is the issue markdown file under `./issues/`.
- **No edits to source**: do NOT use the Edit or Write tools on any file outside `./issues/`. If you accidentally start editing source code, revert immediately.
- Write reports under `./issues/` at the repo root.
- Use `NNNN-short-slug.md` for normal issues and `BLOCK-NNN-short-slug.md` for blocking issues.
- Pick the next unused number for the chosen prefix.
- Back claims with concrete evidence: `path:line`, call chains, grep results, docs, tests, or runtime output.
- Do not commit unless the user explicitly asks. If asked, commit only the issue file.
- **Recommendations in the report** may describe code changes, but must NOT implement them. The report is a prescription, not a treatment.

## Workflow

1. Identify the exact bug, gap, or code area the user wants analyzed.
2. Gather evidence from code, tests, docs, and runtime output. Use parallel searches/agents when useful.
3. Trace the relevant flow end to end, such as UI -> API -> service -> repository -> storage.
4. Classify the root cause and severity.
5. Write a concise markdown report in `./issues/`. **Do NOT implement any fixes.**

## Severity

| Level | Meaning |
|---|---|
| P0 阻断 | Crash, data loss, auth bypass, security issue, or release blocker. |
| P1 严重 | Core feature broken, wrong results, data inconsistency, no practical workaround. |
| P2 中等 | Partial breakage, degraded UX, missing guardrail, workaround exists. |
| P3 轻微 | Cosmetic issue, dead code, minor design drift, little or no user impact. |
| P4 建议 | Refactor, cleanup, docs, or future-proofing suggestion. |

## Report Template

```markdown
# Issue <NNNN / BLOCK-NNN>: <Title>

**Status**: 待办
**发现时间**: YYYY-MM-DD
**严重等级**: <P0/P1/P2/P3/P4>
**类型**: <Root-cause category>
**影响范围**: `<modules/packages>`

## 问题描述

<What is broken and why it matters.>

## 调用链 / 数据流

<Entry point -> component/service -> failing point>

## 直接证据

<Concrete file:line references, logs, grep output, tests, or docs.>

## 根因分析

<Why the problem exists. Distinguish evidence from assumptions.>

## 推荐方案

<1-3 concrete options. Mark one as 推荐 when clear.>

## 不修复的影响

<Realistic impact and blast radius if left unresolved.>

## 相关文件

| 文件 | 角色 |
|---|---|
| `path/to/file.py:123` | <Role in this issue> |
```

## Notes

- Common root-cause categories: dead code, plan-implementation gap, missing integration, incorrect assumption, ordering/race issue, missing validation, schema drift, edge-case gap, architecture violation.
- If the user later asks to fix the issue, leave analysis mode and follow normal coding rules.
- **Reminder: this skill is analysis-only.** Even if you think a fix is trivial, do not touch source code. The Rules section above is absolute — no edits, no writes, no patches to any file outside `./issues/`.
