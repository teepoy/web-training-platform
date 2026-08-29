import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import RangeFilterMenu from "./RangeFilterMenu.vue";

describe("RangeFilterMenu", () => {
  it("clears only the draft and cancels without applying", async () => {
    const { wrapper } = await mountWithProviders(RangeFilterMenu, {
      props: { min: 10, max: 20 },
    });

    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Clear")
      ?.trigger("click");
    expect(wrapper.emitted("update:min")?.at(-1)?.[0]).toBeNull();
    expect(wrapper.emitted("update:max")?.at(-1)?.[0]).toBeNull();
    expect(wrapper.emitted("apply")).toBeUndefined();

    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Cancel")
      ?.trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
    expect(wrapper.emitted("apply")).toBeUndefined();
  });

  it("does not apply a partial or inverted range", async () => {
    const partial = await mountWithProviders(RangeFilterMenu, {
      props: { min: 10, max: null },
    });
    const inverted = await mountWithProviders(RangeFilterMenu, {
      props: { min: 20, max: 10 },
    });

    expect(
      partial.wrapper
        .findAll("button")
        .find((button) => button.text() === "Apply")
        ?.attributes("disabled"),
    ).toBeDefined();
    expect(
      inverted.wrapper
        .findAll("button")
        .find((button) => button.text() === "Apply")
        ?.attributes("disabled"),
    ).toBeDefined();
  });
});
