import { describe, expect, it, vi } from "vitest";
import type {
  DatasetCollectionMembershipResponse,
  DatasetCollectionResponse,
} from "@/generated/orval/models";
import {
  createCollectionWithMembers,
  haveMatchingOrderedLabelSpaces,
  type DatasetCollectionCreationApi,
} from "./createCollectionWithMembers";

const collection: DatasetCollectionResponse = {
  id: "collection-1",
  org_id: "org-1",
  name: "Collection",
  description: "",
  target_view_id: "patch_image_v1",
  target_view_contract: "sc.patch-image",
  target_schema_version: "1",
  duplicate_policy: "keep_all",
  missing_data_policy: "fail",
  definition_version: 0,
  created_by: "user-1",
  created_at: "2026-08-12T00:00:00Z",
  updated_at: "2026-08-12T00:00:00Z",
};

function api(overrides: Partial<DatasetCollectionCreationApi> = {}): DatasetCollectionCreationApi {
  return {
    create: vi.fn().mockResolvedValue(collection),
    link: vi.fn().mockResolvedValue({
      collection: { ...collection, definition_version: 1 },
      members: [],
    } satisfies DatasetCollectionMembershipResponse),
    remove: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

describe("createCollectionWithMembers", () => {
  it("returns the linked definition when members were requested", async () => {
    const client = api();
    const result = await createCollectionWithMembers(
      {
        name: "Collection",
        description: "",
        targetViewId: "patch_image_v1",
        sourceDatasetIds: ["dataset-1"],
      },
      client,
    );

    expect(result.definition_version).toBe(1);
    expect(client.link).toHaveBeenCalledWith(collection, ["dataset-1"]);
    expect(client.remove).not.toHaveBeenCalled();
  });

  it("removes the new empty collection when linking fails", async () => {
    const linkError = new Error("incompatible members");
    const client = api({ link: vi.fn().mockRejectedValue(linkError) });

    await expect(
      createCollectionWithMembers(
        {
          name: "Collection",
          description: "",
          targetViewId: "patch_image_v1",
          sourceDatasetIds: ["dataset-1"],
        },
        client,
      ),
    ).rejects.toBe(linkError);
    expect(client.remove).toHaveBeenCalledWith("collection-1");
  });
});

describe("haveMatchingOrderedLabelSpaces", () => {
  it("requires the exact same label order", () => {
    expect(
      haveMatchingOrderedLabelSpaces([
        {
          task_spec: {
            task_type: "sc",
            label_space: ["clean", "defect"],
            metadata_schema: {},
          },
        },
        {
          task_spec: {
            task_type: "sc",
            label_space: ["clean", "defect"],
            metadata_schema: {},
          },
        },
      ]),
    ).toBe(true);
    expect(
      haveMatchingOrderedLabelSpaces([
        {
          task_spec: {
            task_type: "sc",
            label_space: ["clean", "defect"],
            metadata_schema: {},
          },
        },
        {
          task_spec: {
            task_type: "sc",
            label_space: ["defect", "clean"],
            metadata_schema: {},
          },
        },
      ]),
    ).toBe(false);
  });
});
