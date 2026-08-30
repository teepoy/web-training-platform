import { describe, expect, it } from "vitest";
import { NDatePicker, NInputNumber, NSlider } from "naive-ui";
import { mountWithProviders } from "@/testing";
import RangeFilterMenu from "./RangeFilterMenu.vue";
import type { DateTimeRangeFilterDescriptor, NumericRangeFilterDescriptor } from "./rangeFilter";

const numericDescriptor: NumericRangeFilterDescriptor = {
  kind: "number",
  bounds: { min: 0, max: 100 },
  step: 0.001,
  displayPrecision: 3,
};
const dateTimeDescriptor: DateTimeRangeFilterDescriptor = {
  kind: "datetime",
  timeZone: "browser",
  interval: "[start,end)",
};

function button(wrapper: Awaited<ReturnType<typeof mountWithProviders>>["wrapper"], label: string) {
  return wrapper.findAll("button").find((candidate) => candidate.text() === label);
}

describe("RangeFilterMenu", () => {
  it("synchronizes the numeric slider and precise number inputs", async () => {
    const { wrapper } = await mountWithProviders(RangeFilterMenu, {
      props: { descriptor: numericDescriptor, min: 10.125, max: 20.875 },
    });

    const slider = wrapper.findComponent(NSlider);
    expect(slider.props()).toMatchObject({
      min: 0,
      max: 100,
      step: 0.001,
      range: true,
      keyboard: true,
    });
    expect(slider.attributes("aria-label")).toBe("Numeric range slider");
    slider.vm.$emit("update:value", [12.345, 67.891]);
    expect(wrapper.emitted("update:min")?.at(-1)?.[0]).toBe(12.345);
    expect(wrapper.emitted("update:max")?.at(-1)?.[0]).toBe(67.891);

    const inputs = wrapper.findAllComponents(NInputNumber);
    inputs[0]!.vm.$emit("update:value", 12.34567);
    inputs[1]!.vm.$emit("update:value", 67.89123);
    expect(wrapper.emitted("update:min")?.at(-1)?.[0]).toBe(12.34567);
    expect(wrapper.emitted("update:max")?.at(-1)?.[0]).toBe(67.89123);
    expect(inputs[0]!.props("precision")).toBeUndefined();
  });

  it("clears only the draft and cancels without applying", async () => {
    const { wrapper } = await mountWithProviders(RangeFilterMenu, {
      props: { descriptor: numericDescriptor, min: 10, max: 20 },
    });

    await button(wrapper, "Clear")?.trigger("click");
    expect(wrapper.emitted("update:min")?.at(-1)?.[0]).toBeNull();
    expect(wrapper.emitted("update:max")?.at(-1)?.[0]).toBeNull();
    expect(wrapper.emitted("apply")).toBeUndefined();

    await button(wrapper, "Cancel")?.trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
    expect(wrapper.emitted("apply")).toBeUndefined();
  });

  it.each([
    { min: 10, max: null, name: "partial" },
    { min: 20, max: 10, name: "inverted" },
    { min: Number.NaN, max: 10, name: "non-finite" },
    { min: -1, max: 10, name: "below observed bounds" },
    { min: 10, max: 101, name: "above observed bounds" },
  ])("does not apply a $name numeric range", async ({ min, max }) => {
    const { wrapper } = await mountWithProviders(RangeFilterMenu, {
      props: { descriptor: numericDescriptor, min, max },
    });

    expect(button(wrapper, "Apply")?.attributes("disabled")).toBeDefined();
  });

  it("does not invent a slider when observed bounds are unavailable", async () => {
    const { wrapper } = await mountWithProviders(RangeFilterMenu, {
      props: {
        descriptor: { ...numericDescriptor, bounds: null },
        min: 10.25,
        max: 20.75,
        rangeUnavailable: true,
      },
    });

    expect(wrapper.findComponent(NSlider).exists()).toBe(false);
    expect(wrapper.text()).toContain("Could not load field range");
    expect(wrapper.findAllComponents(NInputNumber)).toHaveLength(2);
    expect(button(wrapper, "Apply")?.attributes("disabled")).toBeUndefined();
  });

  it("disables range editing and apply while observed bounds are loading", async () => {
    const { wrapper } = await mountWithProviders(RangeFilterMenu, {
      props: { descriptor: numericDescriptor, min: 10, max: 20, loading: true },
    });

    expect(wrapper.text()).toContain("Querying field range");
    expect(wrapper.findComponent(NSlider).props("disabled")).toBe(true);
    expect(wrapper.findAllComponents(NInputNumber).every((input) => input.props("disabled"))).toBe(
      true,
    );
    expect(button(wrapper, "Apply")?.attributes("disabled")).toBeDefined();
  });

  it("uses one localized datetime range picker and preserves its half-open endpoints", async () => {
    const start = Date.UTC(2026, 7, 1, 0, 0);
    const end = Date.UTC(2026, 7, 2, 0, 0);
    const { wrapper } = await mountWithProviders(RangeFilterMenu, {
      props: { descriptor: dateTimeDescriptor, min: start, max: end },
    });

    const picker = wrapper.findComponent(NDatePicker);
    expect(picker.props("type")).toBe("datetimerange");
    expect(picker.props("value")).toEqual([start, end]);
    expect(picker.attributes("aria-label")).toBe("Date and time range");
    expect(wrapper.text()).toContain("[start,end)");

    const nextStart = start + 3_600_000;
    const nextEnd = end + 3_600_000;
    picker.vm.$emit("update:value", [nextStart, nextEnd]);
    expect(wrapper.emitted("update:min")?.at(-1)?.[0]).toBe(nextStart);
    expect(wrapper.emitted("update:max")?.at(-1)?.[0]).toBe(nextEnd);

    picker.vm.$emit("update:value", null);
    expect(wrapper.emitted("update:min")?.at(-1)?.[0]).toBeNull();
    expect(wrapper.emitted("update:max")?.at(-1)?.[0]).toBeNull();
  });

  it("rejects partial and inverted datetime intervals", async () => {
    const partial = await mountWithProviders(RangeFilterMenu, {
      props: { descriptor: dateTimeDescriptor, min: Date.UTC(2026, 7, 2), max: null },
    });
    const inverted = await mountWithProviders(RangeFilterMenu, {
      props: {
        descriptor: dateTimeDescriptor,
        min: Date.UTC(2026, 7, 2),
        max: Date.UTC(2026, 7, 1),
      },
    });

    expect(button(partial.wrapper, "Apply")?.attributes("disabled")).toBeDefined();
    expect(button(inverted.wrapper, "Apply")?.attributes("disabled")).toBeDefined();
  });
});
