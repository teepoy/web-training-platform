import { describe, expect, it, vi } from "vitest";
import { mountWithProviders } from "@/testing";
import ScTextFilterMenu from "./ScTextFilterMenu.vue";

describe("ScTextFilterMenu", () => {
  it("loads IDs from a file into the draft and applies them", async () => {
    const { wrapper } = await mountWithProviders(ScTextFilterMenu, {
      props: { appliedValues: [] },
    });
    const input = wrapper.get<HTMLInputElement>('input[type="file"]');
    const file = { name: "selected.csv", text: vi.fn(async () => "defect_id\n42\n87\n42") };
    Object.defineProperty(input.element, "files", { value: [file], configurable: true });

    await input.trigger("change");
    await vi.waitFor(() => expect(wrapper.text()).toContain("Loaded 2 unique IDs"));
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Apply")
      ?.trigger("click");

    expect(wrapper.emitted("apply")).toEqual([[[42, 87]]]);
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("keeps the filter open when a file has no valid IDs", async () => {
    const { wrapper } = await mountWithProviders(ScTextFilterMenu, {
      props: { appliedValues: [] },
    });
    const input = wrapper.get<HTMLInputElement>('input[type="file"]');
    const file = { name: "bad.txt", text: vi.fn(async () => "not-an-id") };
    Object.defineProperty(input.element, "files", { value: [file], configurable: true });

    await input.trigger("change");
    await vi.waitFor(() => expect(wrapper.text()).toContain("contains no valid integer"));

    expect(wrapper.emitted("apply")).toBeUndefined();
    expect(wrapper.emitted("close")).toBeUndefined();
  });

  it("imports and applies a large ID file without truncation", async () => {
    const values = Array.from({ length: 20_000 }, (_, index) => index + 1);
    const { wrapper } = await mountWithProviders(ScTextFilterMenu, {
      props: { appliedValues: [] },
    });
    const input = wrapper.get<HTMLInputElement>('input[type="file"]');
    const file = { name: "large.txt", text: vi.fn(async () => values.join("\n")) };
    Object.defineProperty(input.element, "files", { value: [file], configurable: true });

    await input.trigger("change");
    await vi.waitFor(() => expect(wrapper.text()).toContain("Loaded 20,000 unique IDs"));
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Apply")
      ?.trigger("click");

    const applied = wrapper.emitted("apply")?.[0]?.[0];
    expect(applied).toHaveLength(20_000);
    expect(applied?.[0]).toBe(1);
    expect(applied?.[19_999]).toBe(20_000);
  });
});
