import { describe, it, expect } from "vitest";
import { ref } from "vue";
import { createDataPipeline } from "./useDataPipeline";

interface TestItem {
  id: string;
  [key: string]: unknown;
}

describe("useDataPipeline", () => {
  it("createDataPipeline returns expected API shape", () => {
    const pipeline = createDataPipeline(ref<TestItem[]>([{ id: "a" }, { id: "b" }]));

    expect(pipeline).toHaveProperty("rawItems");
    expect(pipeline).toHaveProperty("register");
    expect(pipeline).toHaveProperty("getNode");
    expect(pipeline).toHaveProperty("nodes");

    expect(typeof pipeline.register).toBe("function");
    expect(typeof pipeline.getNode).toBe("function");
  });

  it("register creates a root node with null parentId and empty annotation", () => {
    const pipeline = createDataPipeline(ref<TestItem[]>([{ id: "a" }]));
    const node = pipeline.register("wafer");

    expect(node.id).toBe("wafer");
    expect(node.parentId).toBeNull();
    expect(node.annotation.value).toBeNull();
    expect(node.visibleAnnotations.value).toEqual([]);
  });

  it("register with parentId creates a child node with correct parent linkage", () => {
    const pipeline = createDataPipeline(ref<TestItem[]>([{ id: "a" }]));
    const wafer = pipeline.register("wafer");
    const gallery = pipeline.register("gallery", "wafer");

    expect(gallery.parentId).toBe("wafer");
    expect(wafer.child.value?.id).toBe("gallery");
    expect(gallery.child.value).toBeNull();
  });

  it("annotate sets annotation.kind and ids Set on the node", () => {
    const pipeline = createDataPipeline(ref<TestItem[]>([{ id: "a" }, { id: "b" }]));
    const node = pipeline.register("wafer");

    node.annotate("selected", ["a", "b"]);

    expect(node.annotation.value).not.toBeNull();
    expect(node.annotation.value!.kind).toBe("selected");
    expect(node.annotation.value!.ids.size).toBe(2);
    expect(node.annotation.value!.ids.has("a")).toBe(true);
    expect(node.annotation.value!.ids.has("b")).toBe(true);
  });

  it("visibleAnnotations auto-collects along parent chain", () => {
    const pipeline = createDataPipeline(ref<TestItem[]>([{ id: "a" }, { id: "b" }]));
    const wafer = pipeline.register("wafer");
    const gallery = pipeline.register("gallery", "wafer");

    wafer.annotate("selected", ["a"]);

    // gallery's visibleAnnotations should include wafer's annotation
    expect(gallery.visibleAnnotations.value.length).toBe(1);
    expect(gallery.visibleAnnotations.value[0].kind).toBe("selected");
    expect(gallery.visibleAnnotations.value[0].ids.has("a")).toBe(true);
  });

  it("clear resets annotation to null and visibleAnnotations to empty", () => {
    const pipeline = createDataPipeline(ref<TestItem[]>([{ id: "a" }]));
    const node = pipeline.register("wafer");

    node.annotate("selected", ["a"]);
    expect(node.annotation.value).not.toBeNull();
    expect(node.visibleAnnotations.value.length).toBe(1);

    node.clear();

    expect(node.annotation.value).toBeNull();
    expect(node.visibleAnnotations.value).toEqual([]);
  });

  it("independent chains do not interfere with each other", () => {
    const pipeline = createDataPipeline(ref<TestItem[]>([{ id: "a" }, { id: "b" }]));

    // Chain 1: wafer → gallery
    const wafer = pipeline.register("wafer");
    const gallery = pipeline.register("gallery", "wafer");

    // Chain 2: scatter → other
    const scatter = pipeline.register("scatter");
    const other = pipeline.register("other", "scatter");

    // Annotate only chain 1
    wafer.annotate("selected", ["a"]);

    // Chain 2 should remain unannotated
    expect(scatter.annotation.value).toBeNull();
    expect(scatter.visibleAnnotations.value).toEqual([]);
    expect(other.annotation.value).toBeNull();
    expect(other.visibleAnnotations.value).toEqual([]);

    // Chain 1 should see the annotation
    expect(wafer.annotation.value).not.toBeNull();
    expect(wafer.annotation.value!.kind).toBe("selected");
    expect(gallery.visibleAnnotations.value.length).toBe(1);
    expect(gallery.visibleAnnotations.value[0].kind).toBe("selected");

    // Annotate chain 2
    scatter.annotate("excluded", ["b"]);

    // Chain 2 should now have annotation, chain 1 unaffected
    expect(scatter.annotation.value).not.toBeNull();
    expect(scatter.annotation.value!.kind).toBe("excluded");
    expect(other.visibleAnnotations.value.length).toBe(1);
    expect(other.visibleAnnotations.value[0].kind).toBe("excluded");

    // Chain 1 still has its own annotation
    expect(gallery.visibleAnnotations.value.length).toBe(1);
    expect(gallery.visibleAnnotations.value[0].kind).toBe("selected");
  });
});
