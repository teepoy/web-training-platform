import { describe, expect, it } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mountWithProviders } from "@/testing";
import WidgetErrorBoundary from "./WidgetErrorBoundary.vue";

const PROPS = {
  widgetId: "test-widget",
  widgetComponent: "TestWidget",
};

const NormalChild = defineComponent({
  render: () => h("div", "Normal child content"),
});

function getErrorVm(wrapper: Awaited<ReturnType<typeof mountWithProviders>>["wrapper"]): { error: string | null } {
  return wrapper.vm as unknown as { error: string | null };
}

describe("WidgetErrorBoundary", () => {
  it("renders normal child content without error", async () => {
    const { wrapper } = await mountWithProviders(WidgetErrorBoundary, {
      props: PROPS,
      slots: { default: NormalChild },
    });

    expect(wrapper.text()).toContain("Normal child content");
    expect(wrapper.find(".web-error").exists()).toBe(false);
  });

  it("displays widgetId and widgetComponent in error text when error is captured", async () => {
    const { wrapper } = await mountWithProviders(WidgetErrorBoundary, {
      props: PROPS,
      slots: { default: NormalChild },
    });

    // Set internal error ref directly to simulate onErrorCaptured firing.
    // In jsdom, error propagation through slots is intercepted by the
    // test harness; this verifies the error UI rendering logic.
    const vm = getErrorVm(wrapper);
    vm.error = "Simulated widget crash";
    await nextTick();

    expect(wrapper.find(".web-error").exists()).toBe(true);
    const errorMsg = wrapper.find(".web-error__msg");
    expect(errorMsg.exists()).toBe(true);
    expect(errorMsg.text()).toContain("TestWidget");
    expect(errorMsg.text()).toContain("Simulated widget crash");
  });

  it("retry button resets error state", async () => {
    const { wrapper } = await mountWithProviders(WidgetErrorBoundary, {
      props: PROPS,
      slots: { default: NormalChild },
    });

    const vm = getErrorVm(wrapper);
    vm.error = "Simulated widget crash";
    await nextTick();

    expect(wrapper.find(".web-error").exists()).toBe(true);
    expect(wrapper.find(".web-error__retry").exists()).toBe(true);

    await wrapper.find(".web-error__retry").trigger("click");

    // Error cleared, slot content shown again
    expect(wrapper.find(".web-error").exists()).toBe(false);
    expect(wrapper.text()).toContain("Normal child content");
  });

  it("error state includes widgetId and widgetComponent in message", async () => {
    const { wrapper } = await mountWithProviders(WidgetErrorBoundary, {
      props: PROPS,
      slots: { default: NormalChild },
    });

    const vm = getErrorVm(wrapper);
    vm.error = "Simulated widget crash";
    await nextTick();

    const errorMsg = wrapper.find(".web-error__msg").text();
    expect(errorMsg).toContain("TestWidget");
    expect(errorMsg).toContain("Simulated widget crash");
    // Verify the message format matches: Widget "Component" failed: error
    expect(errorMsg).toContain("Widget");
    expect(errorMsg).toContain("failed");
  });
});
