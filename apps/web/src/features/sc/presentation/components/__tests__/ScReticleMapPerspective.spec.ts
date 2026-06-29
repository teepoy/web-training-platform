import { describe, it, expect } from "vitest";
import { mountWithProviders } from "@/testing";
import ScReticleMapPerspective from "../ScReticleMapPerspective.vue";
import { makePerspectiveStride6Points, makeHighlightDefects } from "./perspectiveMapFixtures";
import type { HighlightDefect } from "../types";

describe("ScReticleMapPerspective", () => {
  it("mounts and renders container with overlay canvas", async () => {
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective);
    expect(wrapper.find(".sc-reticle-map-perspective").exists()).toBe(true);
    expect(wrapper.find(".sc-reticle-map-perspective__overlay").exists()).toBe(true);
  });

  it("accepts highlightDefects prop without error", async () => {
    const hd = makeHighlightDefects(2);
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective, {
      props: { highlightDefects: hd },
    });
    expect(wrapper.props("highlightDefects")).toEqual(hd);
  });

  it("renders without error when highlightDefects is undefined", async () => {
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective);
    expect(wrapper.exists()).toBe(true);
    expect(wrapper.props("highlightDefects")).toBeUndefined();
  });

  it("receives highlightDefects with reticleX and reticleY coordinates", async () => {
    const hd: HighlightDefect[] = [
      { defectId: 1, waferX: 1000, waferY: 2000, dieX: 100, dieY: 200, reticleX: 55, reticleY: 77 },
    ];
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective, {
      props: { highlightDefects: hd, mode: "select" },
    });
    const prop = wrapper.props("highlightDefects") as HighlightDefect[];
    expect(prop).toHaveLength(1);
    expect(prop[0].reticleX).toBe(55);
    expect(prop[0].reticleY).toBe(77);
  });

  it("handles pointer events without crashing", async () => {
    const { packed } = makePerspectiveStride6Points({ count: 3 });
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective, {
      props: { points: packed, mode: "select" },
    });
    const overlay = wrapper.find(".sc-reticle-map-perspective__overlay");
    await overlay.trigger("pointerdown", { clientX: 50, clientY: 50, button: 0 });
    await overlay.trigger("pointermove", { clientX: 100, clientY: 100 });
    await overlay.trigger("pointerup", { clientX: 100, clientY: 100 });
    expect(wrapper.exists()).toBe(true);
  });

  it("clears immediateCrosshairPoints on pointerDown", async () => {
    const { packed } = makePerspectiveStride6Points({ count: 3 });
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective, {
      props: { points: packed, mode: "select" },
    });
    const vm = wrapper.vm as unknown as { immediateCrosshairPoints: { x: number; y: number }[] };
    vm.immediateCrosshairPoints = [{ x: 100, y: 200 }];
    const overlay = wrapper.find(".sc-reticle-map-perspective__overlay");
    await overlay.trigger("pointerdown", { clientX: 50, clientY: 50, button: 0 });
    expect(vm.immediateCrosshairPoints).toEqual([]);
  });

  it("emits box-select in select mode on drag release", async () => {
    const { packed } = makePerspectiveStride6Points({ count: 3 });
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective, {
      props: { points: packed, mode: "select" },
    });
    const overlay = wrapper.find(".sc-reticle-map-perspective__overlay");
    await overlay.trigger("pointerdown", { clientX: 10, clientY: 10, button: 0 });
    await overlay.trigger("pointermove", { clientX: 200, clientY: 200 });
    await overlay.trigger("pointerup", { clientX: 200, clientY: 200 });
    expect(wrapper.emitted("box-select")).toBeTruthy();
  });

  it("emits zoom-in in zoomin mode on drag release", async () => {
    const { packed } = makePerspectiveStride6Points({ count: 3 });
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective, {
      props: { points: packed, mode: "zoomin" },
    });
    const overlay = wrapper.find(".sc-reticle-map-perspective__overlay");
    await overlay.trigger("pointerdown", { clientX: 10, clientY: 10, button: 0 });
    await overlay.trigger("pointermove", { clientX: 200, clientY: 200 });
    await overlay.trigger("pointerup", { clientX: 200, clientY: 200 });
    expect(wrapper.emitted("zoom-in")).toBeTruthy();
  });

  it("clears immediateCrosshairPoints when mode changes", async () => {
    const { packed } = makePerspectiveStride6Points({ count: 3 });
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective, {
      props: { points: packed, mode: "select" },
    });
    const vm = wrapper.vm as unknown as { immediateCrosshairPoints: { x: number; y: number }[] };
    vm.immediateCrosshairPoints = [{ x: 100, y: 200 }];
    await wrapper.setProps({ mode: "zoomin" });
    expect(vm.immediateCrosshairPoints).toEqual([]);
  });

  it("clears immediateCrosshairPoints when points change", async () => {
    const { packed } = makePerspectiveStride6Points({ count: 3 });
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective, {
      props: { points: packed, mode: "select" },
    });
    const vm = wrapper.vm as unknown as { immediateCrosshairPoints: { x: number; y: number }[] };
    vm.immediateCrosshairPoints = [{ x: 100, y: 200 }];
    const { packed: newPacked } = makePerspectiveStride6Points({ count: 5 });
    await wrapper.setProps({ points: newPacked });
    expect(vm.immediateCrosshairPoints).toEqual([]);
  });

  it("emits empty selection-change on dblclick in select mode", async () => {
    const { wrapper } = await mountWithProviders(ScReticleMapPerspective, {
      props: { mode: "select" },
    });
    const container = wrapper.find(".sc-reticle-map-perspective");
    await container.trigger("dblclick");
    expect(wrapper.emitted("selection-change")).toBeTruthy();
    expect(wrapper.emitted("selection-change")?.[0]).toEqual([[]]);
  });
});
