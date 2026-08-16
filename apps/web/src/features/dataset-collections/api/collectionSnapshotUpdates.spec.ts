import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/testing/msw/server";
import {
  getCollectionSnapshotUpdateStatus,
  refreshCollectionSnapshot,
} from "./collectionSnapshotUpdates";

describe("collection snapshot update API", () => {
  it("loads member revision differences", async () => {
    server.use(
      http.get("/api/v1/dataset-collections/collection-1/snapshot-update-status", () =>
        HttpResponse.json({
          snapshot_id: "snapshot-4",
          snapshot_revision_number: 4,
          update_available: true,
          outdated_member_count: 1,
          members: [
            {
              member_id: "member-1",
              dataset_id: "dataset-1",
              observed_dataset_revision_id: "revision-1",
              observed_dataset_revision_number: 1,
              current_dataset_revision_id: "revision-2",
              current_dataset_revision_number: 2,
              update_available: true,
            },
          ],
        }),
      ),
    );

    const status = await getCollectionSnapshotUpdateStatus("collection-1");

    expect(status.outdated_member_count).toBe(1);
    expect(status.members[0]?.current_dataset_revision_id).toBe("revision-2");
  });

  it("requests an explicit refresh with the current definition version", async () => {
    let body: unknown;
    server.use(
      http.post(
        "/api/v1/dataset-collections/collection-1/refresh-snapshot",
        async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({ outcome: "unchanged", snapshot: { id: "snapshot-4" } });
        },
      ),
    );

    const result = await refreshCollectionSnapshot("collection-1", {
      expected_definition_version: 7,
    });

    expect(body).toEqual({ expected_definition_version: 7 });
    expect(result.outcome).toBe("unchanged");
  });
});
