import { nextTick } from "vue";
import { describe, expect, it } from "vitest";
import { NInputNumber } from "naive-ui";
import { mountWithProviders } from "@/testing";
import { SC_REVIEW_SAMPLING_RULE_CATALOG } from "@/features/sc/domain/samplingRules";
import ClusterPercentageRuleEditor from "./ClusterPercentageRuleEditor.vue";
import { SC_SAMPLING_RULE_EDITORS } from "./samplingRuleEditors";

describe("SC sampling rule editors", () => {
  it("gives every business rule its own concrete editor component", () => {
    const ruleIds = SC_REVIEW_SAMPLING_RULE_CATALOG.map((item) => item.id);
    const editorIds = Object.keys(SC_SAMPLING_RULE_EDITORS);
    const concreteEditors = Object.values(SC_SAMPLING_RULE_EDITORS).map(
      (descriptor) => descriptor.component,
    );

    expect(editorIds).toEqual(ruleIds);
    expect(new Set(concreteEditors).size).toBe(17);
  });

  it("edits a percentage while keeping floor rounding implicit", async () => {
    const { wrapper } = await mountWithProviders(ClusterPercentageRuleEditor, {
      props: {
        rule: { type: "cluster_percentage", percentage: 10, rounding: "floor" },
        context: { classCodeOptions: [], finalClassOptions: [], loading: false },
      },
    });

    expect(wrapper.text()).not.toContain("Rounding");
    wrapper.findComponent(NInputNumber).vm.$emit("update:value", 25);
    await nextTick();
    expect(wrapper.emitted("update:rule")?.at(-1)?.[0]).toEqual({
      type: "cluster_percentage",
      percentage: 25,
      rounding: "floor",
    });
  });
});
