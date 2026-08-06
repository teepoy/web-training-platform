import { describe, expect, it } from "vitest";
import { NCheckbox, NInput } from "naive-ui";
import { mountWithProviders } from "@/testing";
import ScSetFilterMenu from "./ScSetFilterMenu.vue";

describe("ScSetFilterMenu", () => {
  it("selects and clears every currently visible option", async () => {
    const { wrapper } = await mountWithProviders(ScSetFilterMenu, {
      props: {
        search: "ap",
        appliedValues: [],
        draftValues: ["2"],
        options: [
          { label: "Apple", value: 1 },
          { label: "Banana", value: 2 },
          { label: "Apricot", value: 3 },
        ],
      },
    });

    const selectAll = wrapper.findComponent(NCheckbox);
    expect(selectAll.text()).toBe("Select all (2)");
    selectAll.vm.$emit("update:checked", true);
    expect(wrapper.emitted("update:draftValues")?.at(-1)?.[0]).toEqual(["2", "1", "3"]);

    await wrapper.setProps({ draftValues: ["1", "2", "3"] });
    wrapper.findComponent(NCheckbox).vm.$emit("update:checked", false);
    expect(wrapper.emitted("update:draftValues")?.at(-1)?.[0]).toEqual(["2"]);
  });

  it("shows an indeterminate select-all state for a partial selection", async () => {
    const { wrapper } = await mountWithProviders(ScSetFilterMenu, {
      props: {
        search: "",
        appliedValues: [],
        draftValues: ["1"],
        options: [
          { label: "One", value: 1 },
          { label: "Two", value: 2 },
        ],
      },
    });

    expect(wrapper.findComponent(NCheckbox).props("indeterminate")).toBe(true);
  });

  it("requests remote search and retains values selected on an earlier result page", async () => {
    const { wrapper } = await mountWithProviders(ScSetFilterMenu, {
      props: {
        search: "",
        appliedValues: [],
        draftValues: ["1"],
        options: [{ label: "One", value: 1 }],
      },
    });

    wrapper.findComponent(NInput).vm.$emit("update:value", "two");
    expect(wrapper.emitted("update:search")?.at(-1)?.[0]).toBe("two");
    expect(wrapper.emitted("search-options")?.at(-1)?.[0]).toBe("two");

    await wrapper.setProps({
      search: "two",
      draftValues: ["1", "2"],
      options: [{ label: "Two", value: 2 }],
    });
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Apply")
      ?.trigger("click");

    expect(wrapper.emitted("apply")?.at(-1)?.[0]).toEqual([1, 2]);
  });
});
