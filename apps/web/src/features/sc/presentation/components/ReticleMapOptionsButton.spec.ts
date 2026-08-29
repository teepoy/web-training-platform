import { NButton, NInputNumber } from "naive-ui";
import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import ReticleMapOptionsButton from "./ReticleMapOptionsButton.vue";

const modelValue = {
  xDieCount: 3,
  yDieCount: 5,
  xDieShift: 0,
  yDieShift: 0,
};

async function openSettings() {
  const mounted = await mountWithProviders(ReticleMapOptionsButton, {
    props: {
      modelValue,
      showImageMarkers: true,
      defectSize: 2,
    },
  });
  await mounted.wrapper.get('[data-testid="sc-map-settings"]').trigger("click");
  return mounted.wrapper;
}

function applyButton(wrapper: Awaited<ReturnType<typeof openSettings>>) {
  const button = wrapper
    .findAllComponents(NButton)
    .find((candidate) => candidate.text() === "Apply");
  if (!button) throw new Error("Map settings Apply button was not rendered");
  return button;
}

describe("ReticleMapOptionsButton", () => {
  it("does not emit configuration updates when nothing changed", async () => {
    const wrapper = await openSettings();

    await applyButton(wrapper).trigger("click");

    expect(wrapper.emitted("submit")).toBeUndefined();
    expect(wrapper.emitted("submit-display")).toBeUndefined();
  });

  it("emits only display settings when defect size changes", async () => {
    const wrapper = await openSettings();
    const inputs = wrapper.findAllComponents(NInputNumber);
    expect(inputs).toHaveLength(5);

    inputs[4]?.vm.$emit("update:value", 3);
    await wrapper.vm.$nextTick();
    await applyButton(wrapper).trigger("click");

    expect(wrapper.emitted("submit")).toBeUndefined();
    expect(wrapper.emitted("submit-display")).toEqual([
      [{ showImageMarkers: true, defectSize: 3 }],
    ]);
  });

  it("emits only reticle settings when the layout changes", async () => {
    const wrapper = await openSettings();
    const inputs = wrapper.findAllComponents(NInputNumber);
    expect(inputs).toHaveLength(5);

    inputs[0]?.vm.$emit("update:value", 4);
    await wrapper.vm.$nextTick();
    await applyButton(wrapper).trigger("click");

    expect(wrapper.emitted("submit")).toEqual([
      [{ xDieCount: 4, yDieCount: 5, xDieShift: 0, yDieShift: 0 }],
    ]);
    expect(wrapper.emitted("submit-display")).toBeUndefined();
  });
});
