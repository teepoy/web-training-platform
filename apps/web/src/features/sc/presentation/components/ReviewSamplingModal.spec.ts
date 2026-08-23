import { h, nextTick } from "vue";
import { describe, expect, it } from "vitest";
import { NMessageProvider } from "naive-ui";
import { mountWithProviders } from "@/testing";
import { createDefaultScAnnotationSamplingProgram } from "@/features/sc/domain/samplingRules";
import ReviewSamplingModal from "./ReviewSamplingModal.vue";
import ClusterCountRuleEditor from "./sampling-rules/ClusterCountRuleEditor.vue";

const modalStub = {
  name: "NModal",
  props: ["show", "title"],
  emits: ["update:show"],
  template:
    '<section v-if="show" :aria-label="title"><slot name="header" /><slot /><slot name="footer" /></section>',
};

describe("ReviewSamplingModal", () => {
  it("marks an existing cohort stale when its sampling pipeline changes", async () => {
    const { wrapper } = await mountWithProviders(NMessageProvider, {
      slots: {
        default: () =>
          h(ReviewSamplingModal, {
            show: true,
            loading: false,
            availableCount: 2_500,
            activeCohortCount: 105,
            mapSelectionCount: 0,
            tableSelectionAvailable: false,
            extraFilter: { combinator: "and", items: [] },
            program: createDefaultScAnnotationSamplingProgram(),
            scope: "all",
            loadGroups: async () => [],
          }),
      },
      global: { stubs: { NModal: modalStub } },
    });

    expect(document.body.querySelector('[data-testid="sampling-cohort-stale"]')).toBeNull();
    const removeButtons = Array.from(document.body.querySelectorAll("button")).filter(
      (button) => button.textContent?.trim() === "Remove",
    );
    removeButtons[0]?.click();
    await nextTick();

    expect(
      document.body.querySelector('[data-testid="sampling-cohort-stale"]')?.textContent,
    ).toContain("105");
    expect(
      Array.from(document.body.querySelectorAll("button")).some(
        (button) => button.textContent?.trim() === "Re-apply sampling",
      ),
    ).toBe(true);
    wrapper.unmount();
  });

  it("shows all 17 business rules and adds one typed rule to the active pipeline", async () => {
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
            program: createDefaultScAnnotationSamplingProgram(),
            scope: "all",
            loadGroups: async () => [],
          }),
      },
      global: { stubs: { NModal: modalStub } },
    });
    const modal = wrapper.findComponent(ReviewSamplingModal);

    const addButton = Array.from(document.body.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Add sampling rule"),
    );
    addButton?.click();
    await nextTick();

    expect(document.body.querySelectorAll('[data-testid^="add-sampling-rule-"]')).toHaveLength(17);
    const clusterCount = document.body.querySelector(
      '[data-testid="add-sampling-rule-cluster_count"]',
    ) as HTMLButtonElement | null;
    expect(clusterCount?.disabled).toBe(false);
    clusterCount?.click();
    await nextTick();

    expect(
      document.body.querySelector('[data-testid="sampling-rule-cluster_count"]'),
    ).not.toBeNull();
    const activeRule = document.body.querySelector(
      '[data-testid="sampling-rule-cluster_count"]',
    ) as HTMLElement;
    expect(activeRule.querySelector('[data-testid="rule-editor-cluster_count"]')).not.toBeNull();
    expect(
      Array.from(activeRule.querySelectorAll("button")).some(
        (button) => button.textContent?.trim() === "Edit",
      ),
    ).toBe(false);
    expect(document.body.textContent).toContain("Cluster defects by count");
    expect(document.body.textContent).not.toContain("Random seed");
    const updates = modal.emitted("update:program") ?? [];
    const latest = updates.at(-1)?.[0] as ReturnType<
      typeof createDefaultScAnnotationSamplingProgram
    >;
    expect(latest.rules).toContainEqual({ type: "cluster_count", count: 50 });

    modal.findComponent(ClusterCountRuleEditor).vm.$emit("update:rule", {
      type: "cluster_count",
      count: 75,
    });
    await nextTick();
    const inlineUpdates = modal.emitted("update:program") ?? [];
    const afterInlineEdit = inlineUpdates.at(-1)?.[0] as ReturnType<
      typeof createDefaultScAnnotationSamplingProgram
    >;
    expect(afterInlineEdit.rules).toContainEqual({ type: "cluster_count", count: 75 });
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
              program: createDefaultScAnnotationSamplingProgram(),
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
      global: { stubs: { NModal: modalStub } },
    });
    const modal = wrapper.findComponent(ReviewSamplingModal);

    await nextTick();
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

  it("lets the user reorder pipeline steps and emits the declared order", async () => {
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
            program: {
              extraFilterEnabled: true,
              rules: [
                { type: "per_wafer_limit", limit: 200 },
                {
                  type: "large_defect_percentage",
                  sizeField: "size_d",
                  minimum: 100,
                  percentage: 10,
                  rounding: "floor",
                },
              ],
            },
            scope: "all",
            loadGroups: async () => [],
          }),
      },
      global: { stubs: { NModal: modalStub } },
    });
    const modal = wrapper.findComponent(ReviewSamplingModal);

    await nextTick();
    const moveDown = document.body.querySelector<HTMLButtonElement>(
      '[data-testid="move-sampling-rule-per_wafer_limit-down"]',
    );
    expect(moveDown).not.toBeNull();
    moveDown?.click();
    await nextTick();

    const updates = modal.emitted("update:program") ?? [];
    const latest = updates.at(-1)?.[0] as ReturnType<
      typeof createDefaultScAnnotationSamplingProgram
    >;
    expect(latest.rules.map((rule) => rule.type)).toEqual([
      "large_defect_percentage",
      "per_wafer_limit",
    ]);
    wrapper.unmount();
  });
});
