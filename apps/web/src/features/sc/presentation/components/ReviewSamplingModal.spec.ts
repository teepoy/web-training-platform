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
            tableSelectionAvailable: false,
            extraFilter: { combinator: "and", items: [] },
            program: createDefaultScSamplingProgram(),
            scope: "all",
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
    const allScope = document.body.querySelector('input[value="all"]') as HTMLInputElement | null;
    expect(allScope?.checked).toBe(true);
    const tabs = Array.from(document.body.querySelectorAll<HTMLElement>(".n-tabs-tab"));
    tabs.find((tab) => tab.textContent?.includes("Extra filter"))?.click();
    await nextTick();
    expect(document.body.querySelector('[data-testid="query-add-condition"]')).not.toBeNull();
    expect(document.body.querySelector('[data-testid="query-add-group"]')).not.toBeNull();
    tabs.find((tab) => tab.textContent?.includes("Enabled rules"))?.click();
    await nextTick();
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
    expect(document.body.textContent).not.toContain("Random seed");
    expect(document.body.textContent).not.toContain("Assign draft label");

    const totalRule = Array.from(document.body.querySelectorAll("article")).find((article) =>
      article.textContent?.includes("Total limit"),
    );
    expect(totalRule?.querySelector("button.rule-copy")).toBeNull();
    expect(
      Array.from(totalRule?.querySelectorAll("button") ?? []).some(
        (button) => button.textContent?.trim() === "Edit",
      ),
    ).toBe(false);
    wrapper.unmount();
  });

  it("renders an optional after-sampling tab and honors its confirmation guard", async () => {
    const { wrapper } = await mountWithProviders(NMessageProvider, {
      slots: {
        default: () =>
          h(
            ReviewSamplingModal,
            {
              show: true,
              loading: false,
              availableCount: 100,
              mapSelectionCount: 0,
              tableSelectionAvailable: false,
              extraFilter: { combinator: "and", items: [] },
              program: createDefaultScSamplingProgram(),
              scope: "all",
              confirmDisabled: true,
              loadGroups: async () => [],
            },
            {
              "after-sampling": () =>
                h("div", { "data-testid": "after-sampling-content" }, "Assign draft label"),
            },
          ),
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

    await vi.waitFor(() => expect(document.body.textContent).toContain("After sampling"));
    const afterSamplingTab = Array.from(
      document.body.querySelectorAll<HTMLElement>(".n-tabs-tab"),
    ).find((tab) => tab.textContent?.includes("After sampling"));
    afterSamplingTab?.click();
    await nextTick();

    expect(document.body.querySelector('[data-testid="after-sampling-content"]')).not.toBeNull();
    const applyButton = Array.from(document.body.querySelectorAll("button")).find(
      (button) => button.textContent?.trim() === "Apply sampling",
    );
    expect(applyButton?.disabled).toBe(true);
    expect(modal.emitted("confirm")).toBeUndefined();
    wrapper.unmount();
  });
});
