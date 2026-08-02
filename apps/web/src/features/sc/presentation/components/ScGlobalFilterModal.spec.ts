import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import ScGlobalFilterModal from "./ScGlobalFilterModal.vue";

describe("ScGlobalFilterModal", () => {
  it("shows the shared field editor and forwards filter changes", async () => {
    const { wrapper } = await mountWithProviders(ScGlobalFilterModal, {
      props: {
        show: true,
        filter: {},
        distinctValues: {},
        showReclassifyColumns: true,
      },
      global: {
        stubs: {
          NModal: {
            name: "NModal",
            props: ["show", "title"],
            emits: ["update:show"],
            template: '<section><slot name="header" /><slot /><slot name="footer" /></section>',
          },
          ScGlobalFilterBar: {
            name: "ScGlobalFilterBar",
            props: [
              "filter",
              "distinctValues",
              "numericRanges",
              "numericRangeLoading",
              "showReclassifyColumns",
            ],
            emits: ["update:filter", "search-options", "request-range"],
            template: "<div />",
          },
        },
      },
    });

    const editor = wrapper.findComponent({ name: "ScGlobalFilterBar" });
    expect(editor.props("showReclassifyColumns")).toBe(true);
    editor.vm.$emit("update:filter", {
      area: { filterType: "number", type: "inRange", filter: 10, filterTo: 20 },
    });

    expect(wrapper.emitted("update:filter")).toEqual([
      [{ area: { filterType: "number", type: "inRange", filter: 10, filterTo: 20 } }],
    ]);
  });
});
