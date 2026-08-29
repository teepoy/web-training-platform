import { describe, expect, it } from "vitest";
import { latestReadyCollectionRevision, resourceTargetRequestFields } from "./types";

describe("resource target contract", () => {
  it("pins the latest ready collection revision", () => {
    const revision = latestReadyCollectionRevision([
      { id: "revision-3", status: "building", revision_number: 3 },
      { id: "revision-1", status: "ready", revision_number: 1 },
      { id: "revision-2", status: "ready", revision_number: 2 },
    ]);

    expect(revision?.id).toBe("revision-2");
  });

  it("emits exactly one API resource target", () => {
    expect(
      resourceTargetRequestFields({
        kind: "dataset",
        id: "dataset-1",
        name: "Dataset",
        viewTypes: ["patch_image_v1"],
      }),
    ).toEqual({ dataset_id: "dataset-1" });
    expect(
      resourceTargetRequestFields({
        kind: "collection",
        id: "collection-1",
        name: "Collection",
        viewTypes: ["patch_image_v1"],
        revisionId: "revision-2",
        revisionNumber: 2,
      }),
    ).toEqual({ collection_id: "collection-1", collection_revision_id: "revision-2" });
  });
});
