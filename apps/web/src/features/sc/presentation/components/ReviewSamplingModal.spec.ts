import { h, nextTick } from "vue";
import { describe, expect, it, vi } from "vitest";
import { NMessageProvider } from "naive-ui";
import { mountWithProviders } from "@/testing";
import { createDefaultScSamplingProgram } from "@/features/sc/domain/samplingRules";
import ReviewSamplingModal from "./ReviewSamplingModal.vue";

describe("ReviewSamplingModal", () => {
  it("uses the dual list only to enable rules and keeps their configuration in the main view", async () => {
    const loadGroups = vi.fn(async () => [
      { value: "1", count: 80 },
      { value: "2", count: 20 },
    ]);
    const { wrapper } = await mountWithProviders(NMessageProvider, {
      slots: {
        default: () =>
          h(ReviewSamplingModal, {
            show: true,
            loading: false,
            availableCount: 100,
            mapSelectionCount: 0,
            globalFilter: {},
            program: createDefaultScSamplingProgram(),
            seed: 42,
            reviewOnly: true,
            mapSelectionOnly: false,
            assignDraftLabel: false,
            draftLabel: null,
            codeLabels: [],
            loadGroups,
          }),
      },
      global: {
        stubs: {
          NModal: {
            name: "NModal",
            props: ["show", "title"],
            emits: ["update:show"],
            template:
              '<section v-if="show" :aria-label="title"><slot name="header" /><slot /><slot name="footer" /></section>',
          },
        },
      },
    });
    const modal = wrapper.findComponent(ReviewSamplingModal);

    await vi.waitFor(() => expect(loadGroups).toHaveBeenCalled());
    await vi.waitFor(() => expect(document.body.textContent).toContain("Manage sampling rules"));
    const manageButton = Array.from(document.body.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Manage sampling rules"),
    );
    expect(manageButton).toBeDefined();
    manageButton?.click();
    await nextTick();

    expect(
      document.body.querySelector('[role="listbox"][aria-label="Disabled sampling rules"]'),
    ).not.toBeNull();
    const conditionalRule = Array.from(document.body.querySelectorAll('[role="option"]')).find(
      (option) => option.textContent?.includes("Conditional limit"),
    ) as HTMLButtonElement | undefined;
    conditionalRule?.click();
    await nextTick();
    const enableButton = document.body.querySelector(
      'button[aria-label="Enable selected rule"]',
    ) as HTMLButtonElement | null;
    expect(enableButton?.disabled).toBe(false);
    enableButton?.click();
    await nextTick();

    const updates = modal.emitted("update:program") ?? [];
    const latest = updates.at(-1)?.[0] as ReturnType<typeof createDefaultScSamplingProgram>;
    expect(latest.conditional.enabled).toBe(true);
    expect(document.body.textContent).toContain("Matched max");
  });
});
