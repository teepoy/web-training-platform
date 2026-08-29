import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import GlobalFilterModal from "./GlobalFilterModal.vue";

describe("GlobalFilterModal", () => {
  it("keeps QueryBuilder changes local until the user applies them", async () => {
    const { wrapper } = await mountWithProviders(GlobalFilterModal, {
      props: {
        show: true,
        filter: { combinator: "and", items: [] },
        distinctValues: {},
        showReclassifyColumns: true,
      },
      global: {
        stubs: {
          NModal: {
            name: "NModal",
            props: ["show", "title", "closable"],
            emits: ["update:show"],
            template: '<section><slot name="header" /><slot /><slot name="footer" /></section>',
          },
          GlobalFilterBar: {
            name: "GlobalFilterBar",
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

    const editor = wrapper.findComponent({ name: "GlobalFilterBar" });
    expect(editor.props("showReclassifyColumns")).toBe(true);
    const filter = {
      combinator: "and",
      items: [
        {
          id: "area-filter",
          field: "area",
          condition: { filterType: "number", type: "inRange", filter: 10, filterTo: 20 },
          source: { kind: "manual" },
        },
      ],
    };
    editor.vm.$emit("update:filter", filter);
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("update:filter")).toBeUndefined();
    expect(editor.props("filter")).toEqual(filter);
    document.querySelector<HTMLButtonElement>('[data-testid="sc-global-filter-apply"]')!.click();
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("update:filter")).toEqual([[filter]]);
    expect(wrapper.emitted("update:show")).toEqual([[false]]);
    wrapper.unmount();
  });

  it("discards an unapplied draft when cancelled and reopened", async () => {
    const appliedFilter = {
      combinator: "and" as const,
      items: [
        {
          id: "class-filter",
          field: "class_number",
          condition: { filterType: "set" as const, values: [2] },
          source: { kind: "manual" as const },
        },
      ],
    };
    const draftFilter = {
      combinator: "or" as const,
      items: [
        ...appliedFilter.items,
        {
          id: "rough-bin-filter",
          field: "rough_bin",
          condition: { filterType: "set" as const, values: [3] },
          source: { kind: "manual" as const },
        },
      ],
    };
    const { wrapper } = await mountWithProviders(GlobalFilterModal, {
      props: {
        show: true,
        filter: appliedFilter,
        distinctValues: {},
      },
      global: {
        stubs: {
          NModal: {
            name: "NModal",
            props: ["show", "closable"],
            emits: ["update:show"],
            template: '<section><slot name="header" /><slot /><slot name="footer" /></section>',
          },
          GlobalFilterBar: {
            name: "GlobalFilterBar",
            props: ["filter"],
            emits: ["update:filter", "search-options", "request-range"],
            template: "<div />",
          },
        },
      },
    });
    const editor = wrapper.findComponent({ name: "GlobalFilterBar" });

    editor.vm.$emit("update:filter", draftFilter);
    await wrapper.vm.$nextTick();
    document.querySelector<HTMLButtonElement>('[data-testid="sc-global-filter-cancel"]')!.click();
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("update:filter")).toBeUndefined();
    await wrapper.setProps({ show: false });
    await wrapper.setProps({ show: true });
    expect(editor.props("filter")).toEqual(appliedFilter);
    wrapper.unmount();
  });

  it("discards the draft when the modal closes through X, mask, or Escape", async () => {
    const appliedFilter = { combinator: "and" as const, items: [] };
    const draftFilter = {
      combinator: "and" as const,
      items: [
        {
          id: "rough-bin-filter",
          field: "rough_bin",
          condition: { filterType: "set" as const, values: [2] },
          source: { kind: "manual" as const },
        },
      ],
    };
    const { wrapper } = await mountWithProviders(GlobalFilterModal, {
      props: {
        show: true,
        filter: appliedFilter,
        distinctValues: {},
      },
      global: {
        stubs: {
          NModal: {
            name: "NModal",
            props: ["show", "closable"],
            emits: ["update:show"],
            template: '<section><slot name="header" /><slot /><slot name="footer" /></section>',
          },
          GlobalFilterBar: {
            name: "GlobalFilterBar",
            props: ["filter"],
            emits: ["update:filter", "search-options", "request-range"],
            template: "<div />",
          },
        },
      },
    });
    const editor = wrapper.findComponent({ name: "GlobalFilterBar" });

    editor.vm.$emit("update:filter", draftFilter);
    await wrapper.vm.$nextTick();
    await wrapper.setProps({ show: false });

    expect(wrapper.emitted("update:filter")).toBeUndefined();
    await wrapper.setProps({ show: true });
    expect(editor.props("filter")).toEqual(appliedFilter);
    wrapper.unmount();
  });
});
