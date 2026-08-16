import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import CollectionSnapshotUpdateAlert from "./CollectionSnapshotUpdateAlert.vue";

describe("CollectionSnapshotUpdateAlert", () => {
  it("explains observed revisions and emits an explicit owner refresh", async () => {
    const { wrapper } = await mountWithProviders(CollectionSnapshotUpdateAlert, {
      props: {
        outdatedMemberCount: 2,
        snapshotRevisionNumber: 4,
        canModify: true,
        loading: false,
      },
    });

    expect(wrapper.text()).toContain("Update available");
    expect(wrapper.text()).toContain("2 linked Datasets have newer change numbers");
    expect(wrapper.text()).toContain("does not copy or freeze Dataset data");
    await wrapper.get('[data-testid="refresh-collection-snapshot"]').trigger("click");
    expect(wrapper.emitted("refresh")).toHaveLength(1);
  });

  it("keeps refresh unavailable for a read-only viewer", async () => {
    const { wrapper } = await mountWithProviders(CollectionSnapshotUpdateAlert, {
      props: {
        outdatedMemberCount: 1,
        snapshotRevisionNumber: 2,
        canModify: false,
        loading: false,
      },
    });

    expect(
      wrapper.get('[data-testid="refresh-collection-snapshot"]').attributes("disabled"),
    ).toBeDefined();
    expect(wrapper.text()).toContain("Only the Collection creator can refresh this snapshot");
  });
});
