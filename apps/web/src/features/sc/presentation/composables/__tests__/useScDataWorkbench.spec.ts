import { effectScope, isReactive } from "vue";
import { afterEach, describe, expect, it } from "vitest";
import { useScDataWorkbench } from "../useScDataWorkbench";

describe("useScDataWorkbench", () => {
  const scopes: ReturnType<typeof effectScope>[] = [];

  afterEach(() => {
    for (const scope of scopes) scope.stop();
    scopes.length = 0;
  });

  it("keeps native data source state outside Vue deep reactivity", async () => {
    const scope = effectScope();
    scopes.push(scope);
    const workbench = scope.run(useScDataWorkbench);
    if (!workbench) throw new Error("workbench was not created");

    await workbench.connect({ kind: "reclassify", datasetId: "ds-1" });

    expect(workbench.dataSource.value).not.toBeNull();
    expect(isReactive(workbench.dataSource.value)).toBe(false);
    expect(() => workbench.disconnect()).not.toThrow();
  });

  it("opens an immutable collection revision as one data scope", async () => {
    const scope = effectScope();
    scopes.push(scope);
    const workbench = scope.run(useScDataWorkbench);
    if (!workbench) throw new Error("workbench was not created");

    await workbench.connect({
      kind: "collection",
      collectionId: "collection-1",
      revisionId: "revision-2",
    });

    expect(workbench.dataSource.value?.scopeKey).toBe("collection:collection-1/revision-2");
  });
});
