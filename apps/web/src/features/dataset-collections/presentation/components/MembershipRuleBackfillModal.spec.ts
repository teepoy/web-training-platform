import { afterEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { h } from "vue";
import { NMessageProvider } from "naive-ui";
import { mountWithProviders } from "@/testing";
import { server } from "@/testing/msw/server";
import type { MembershipRuleResponse } from "@/generated/orval/models";
import MembershipRuleBackfillModal from "./MembershipRuleBackfillModal.vue";

const rule: MembershipRuleResponse = {
  id: "rule-1",
  org_id: "org-1",
  collection_id: "collection-1",
  name: "Metal layers",
  status: "active",
  active_version_id: "rule-version-1",
  activated_at: "2026-08-01T00:00:00Z",
  created_by: "user-1",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  active_version: {
    id: "rule-version-1",
    rule_id: "rule-1",
    version: 1,
    connector_id: "connector-1",
    import_profile_version_id: "profile-1",
    condition: {},
    created_by: "user-1",
    created_at: "2026-08-01T00:00:00Z",
  },
};

const wrappers: Array<{ unmount: () => void }> = [];

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
});

async function waitForCondition(condition: () => boolean, timeoutMs = 1000): Promise<void> {
  const startedAt = Date.now();
  while (!condition()) {
    if (Date.now() - startedAt > timeoutMs) throw new Error("Timed out waiting for condition");
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

describe("MembershipRuleBackfillModal", () => {
  it("previews representative records and requires confirmation before importing all matches", async () => {
    let previewBody: Record<string, unknown> | null = null;
    let runBody: Record<string, unknown> | null = null;
    server.use(
      http.post(
        "/api/v1/dataset-collections/collection-1/membership-rules/rule-1/backfill-preview",
        async ({ request }) => {
          previewBody = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({
            as_of_utc: "2026-08-30T08:00:00Z",
            matched_count: 3,
            representative_records: [
              {
                record_key: "inspection-1",
                source_version: null,
                observed_at: "2026-08-20T08:00:00Z",
                display_name: "Inspection one",
                attributes: { layer_id: "M1" },
              },
            ],
          });
        },
      ),
      http.post(
        "/api/v1/dataset-collections/collection-1/membership-rules/rule-1/backfills",
        async ({ request }) => {
          runBody = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({
            id: "backfill-1",
            org_id: "org-1",
            collection_id: "collection-1",
            rule_id: "rule-1",
            rule_version_id: "rule-version-1",
            kind: "backfill",
            status: "completed",
            as_of_utc: "2026-08-30T08:00:00Z",
            range_start_utc: runBody.start_utc,
            range_end_utc: runBody.end_utc,
            timezone: runBody.timezone,
            parent_run_id: null,
            collection_revision_id: "revision-2",
            stats: {},
            error_detail: null,
            created_by: "user-1",
            created_at: "2026-08-30T08:00:00Z",
            completed_at: "2026-08-30T08:00:01Z",
            items: [],
          });
        },
      ),
    );

    const { wrapper } = await mountWithProviders(NMessageProvider, {
      slots: {
        default: () =>
          h(MembershipRuleBackfillModal, {
            show: true,
            collectionId: "collection-1",
            rule,
          }),
      },
      routes: [
        { path: "/", component: MembershipRuleBackfillModal },
        { path: "/automations", name: "automations", component: MembershipRuleBackfillModal },
      ],
      global: { stubs: { teleport: true } },
    });
    wrappers.push(wrapper);

    const submit = () => wrapper.get('[data-testid="backfill-submit"]');
    expect(submit().attributes("disabled")).toBeDefined();
    await wrapper.get('[data-testid="backfill-preview"]').trigger("click");
    await waitForCondition(() => previewBody !== null);
    await waitForCondition(() => wrapper.text().includes("Inspection one"));
    expect(previewBody).toMatchObject({ representative_limit: 5 });
    expect(wrapper.get('[data-testid="backfill-matched-count"]').text()).toBe("3");
    expect(wrapper.text()).toContain("Import all 3 matching records in this range.");
    expect(submit().attributes("disabled")).toBeDefined();

    await wrapper.get('[data-testid="backfill-confirm-all"]').trigger("click");
    await wrapper.vm.$nextTick();
    expect(submit().attributes("disabled")).toBeUndefined();
    await submit().trigger("click");
    await waitForCondition(() => runBody !== null);

    expect(runBody).toEqual({
      start_utc: previewBody?.start_utc,
      end_utc: previewBody?.end_utc,
      timezone: previewBody?.timezone,
    });
    await waitForCondition(() => wrapper.text().includes("View in Automations"));
  });
});
