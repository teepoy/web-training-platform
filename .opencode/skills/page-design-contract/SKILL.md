---
name: page-design-contract
description: Use when the user wants to iterate on page/UI design BEFORE committing to real models, APIs, or business logic. Triggers include "design a new page", "let's sketch the layout", "敲定页面设计", "*.design.vue", "先把视觉定下来". Produces Storybook-previewable page design contract files named `*.design.vue` next to the relevant PageView so both the user and the agent can view and edit the visual baseline.
---

# Page Design Contract Workflow

This skill defines the shared workflow for **visual/UX iteration** on the web app.
It is for the phase where the user wants to **decide what a page looks like and how it flows**, with no real API, no real types, no business wiring.
The output is a long-lived **page design contract**, not a disposable draft.

## When to use

Trigger this skill when the user says things like:

- "design a new page for X"
- "let's sketch the layout first"
- "敲定页面设计 / 先把页面长什么样定下来"
- "make a design contract for the dataset detail screen"
- "*.design.vue"
- "I want to iterate on visuals before wiring anything"

Do NOT use this skill for:

- Real feature implementation (use `features/` and the normal widget/registry conventions)
- Bugfixes on shipped UI
- Backend / data model design

## Core rules (NON-NEGOTIABLE)

1. **Location**: A page design contract lives next to the PageView it governs.
   - Example: `DatasetListView.vue` has `DatasetListView.design.vue` in the same directory.
   - Do not place page design contracts in a centralized `src/drafts/` directory.
2. **Naming**:
   - Component file: `PageName.design.vue`
   - Storybook file: `PageName.design.stories.ts`
   - Optional secondary pieces: `PageName.Section.design.vue`
3. **Self-contained**:
   - Mock data is defined **inline** in the `.design.vue` file (top of `<script setup>`).
   - No imports from `@/features/*`, no Pinia stores, no Vue Query, no `@/shared/api/*`.
   - Importing from `@/shared/components/*` and Nuxt UI (`U*`) is allowed — these are the design system.
   - Tailwind CSS is allowed and encouraged.
4. **Not routed**:
   - Never add a design contract to `apps/web/src/app/router.ts`.
   - Never import a `.design.vue` from production code.
   - Design contracts exist for Storybook preview and as the visual baseline for the adjacent PageView.
5. **Storybook is the preview surface**:
   - Every design contract has a `.stories.ts` file so the user and the agent can both view it via `pnpm storybook` (port 6006).
   - Storybook is configured to pick up `src/**/*.design.stories.ts`.
6. **Types are loose on purpose**:
   - Use simple inline `interface` or `type` declarations for mock data.
   - Do NOT import production types from `@/types.ts` — design contracts must not be coupled to current models.
7. **Implementation sync**:
   - When the user is happy with the design, update the adjacent PageView against real types/APIs/widgets.
   - Keep the `.design.vue` file as the visual contract unless the user explicitly changes the design decision.
   - When changing an existing page's layout, update the `.design.vue` first, then update the real PageView.

## Standard layout

```text
apps/web/src/features/<feature>/presentation/pages/
├── <PageName>View.vue
├── <PageName>View.design.vue
└── <PageName>View.design.stories.ts
```

## File templates

### `<PageName>.design.vue`

```vue
<script setup lang="ts">
// Design-contract-only mock types. Do NOT import from @/types.
interface MockItem {
  id: string;
  title: string;
  status: "ready" | "running" | "failed";
}

const items: MockItem[] = [
  { id: "1", title: "Example A", status: "ready" },
  { id: "2", title: "Example B", status: "running" },
  { id: "3", title: "Example C", status: "failed" },
];
</script>

<template>
  <div class="p-6 space-y-4">
    <h1 class="text-2xl font-semibold">Page Title (DESIGN)</h1>
    <UCard v-for="item in items" :key="item.id">
      <div class="flex items-center justify-between">
        <span>{{ item.title }}</span>
        <UBadge>{{ item.status }}</UBadge>
      </div>
    </UCard>
  </div>
</template>
```

### `<PageName>.design.stories.ts`

```ts
import type { Meta, StoryObj } from "@storybook/vue3";
import PageNameDesign from "./PageName.design.vue";

const meta: Meta<typeof PageNameDesign> = {
  title: "Design Contracts/PageName",
  component: PageNameDesign,
  parameters: { layout: "fullscreen" },
};

export default meta;

type Story = StoryObj<typeof PageNameDesign>;

export const Default: Story = {};
```

## Agent workflow

When triggered:

1. **Confirm scope in one short line**: which page, which states (empty / loaded / error), which interactions matter.
2. **Find or create the adjacent design contract** next to the relevant PageView.
3. **Write `*.design.vue`** with inline mock data and as many variants as the user asked for.
4. **Write `*.design.stories.ts`** with one `Story` per meaningful state (e.g. `Default`, `Empty`, `Loading`, `Error`).
5. **Tell the user how to preview**: `pnpm storybook`, then open `Design Contracts / <PageName>` in the sidebar.
6. **Iterate in place**: subsequent feedback edits the same `.design.vue` / `.stories.ts`. Never update the real PageView until the design contract is accepted.
7. **Do NOT run** `make test`, pyright, ruff, or backend builds for design-contract-only changes — those rules in `AGENTS.md` apply to production code paths. Design contracts are visual-only.

## Anti-patterns

- ❌ Importing real stores, API clients, or `@/types.ts` into a design contract
- ❌ Adding a design contract to the router
- ❌ Putting page design contracts in a centralized drafts directory
- ❌ Letting the real PageView drift away from the adjacent design contract
- ❌ Implementing a design contract in production by renaming — always re-implement against real models
- ❌ Skipping the `.stories.ts` file (without it the user has no preview surface)

## Lifecycle

Design contracts are long-lived. Keep them beside the PageView as the visual baseline. Delete or rewrite a `.design.vue` file only when the page design decision changes explicitly.
