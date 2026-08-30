import { expect, test } from "../../fixtures";
import { makeModel } from "../../mocks/factories";

test("previews rule backfill and reruns selected collection datasets @mock", async ({
  authedPage,
}) => {
  let submittedBody: unknown;
  let backfillPreviewBody: Record<string, unknown> | null = null;
  let backfillRunBody: Record<string, unknown> | null = null;
  await authedPage.route("**/api/v1/dataset-collections/collection-1**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/members")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "member-1",
            collection_id: "collection-1",
            source_dataset_id: "dataset-1",
            position: 0,
            linked_definition_version: 1,
            unlinked_definition_version: null,
            filter_spec: {},
            label_mapping: {},
            sampling_spec: {},
            linked_by: "user-e2e-1",
            linked_at: "2026-08-15T00:00:00Z",
            unlinked_by: null,
            unlinked_at: null,
          },
          {
            id: "member-2",
            collection_id: "collection-1",
            source_dataset_id: "dataset-2",
            position: 1,
            linked_definition_version: 1,
            unlinked_definition_version: null,
            filter_spec: {},
            label_mapping: {},
            sampling_spec: {},
            linked_by: "user-e2e-1",
            linked_at: "2026-08-15T00:00:00Z",
            unlinked_by: null,
            unlinked_at: null,
          },
        ]),
      });
      return;
    }
    if (url.pathname.endsWith("/revisions")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "revision-1",
            collection_id: "collection-1",
            revision_number: 1,
            definition_version: 1,
            definition_hash: "hash-1",
            target_view_id: "patch_image_v1",
            target_view_contract: "sc.patch-image",
            target_schema_version: "1",
            status: "ready",
            members: [
              {
                member_id: "member-1",
                source_dataset_id: "dataset-1",
                dataset_revision_id: "revision-1",
              },
              {
                member_id: "member-2",
                source_dataset_id: "dataset-2",
                dataset_revision_id: "revision-2",
              },
            ],
            manifest_uri: null,
            trigger_kind: "manual",
            trigger_ref: null,
            created_by: "user-e2e-1",
            created_at: "2026-08-15T00:00:00Z",
            error_code: null,
            error_detail: null,
          },
        ]),
      });
      return;
    }
    if (url.pathname.endsWith("/revisions/revision-1")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "revision-1",
          collection_id: "collection-1",
          revision_number: 1,
          definition_version: 1,
          definition_hash: "hash-1",
          target_view_id: "patch_image_v1",
          target_view_contract: "sc.patch-image",
          target_schema_version: "1",
          status: "ready",
          members: [
            {
              member_id: "member-1",
              source_dataset_id: "dataset-1",
              dataset_revision_id: "revision-1",
            },
            {
              member_id: "member-2",
              source_dataset_id: "dataset-2",
              dataset_revision_id: "revision-2",
            },
          ],
          manifest_uri: null,
          trigger_kind: "manual",
          trigger_ref: null,
          created_by: "user-e2e-1",
          created_at: "2026-08-15T00:00:00Z",
          error_code: null,
          error_detail: null,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/prediction-coverage")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            member_id: "member-1",
            dataset_id: "dataset-1",
            expected_dataset_revision_id: "revision-1",
            status: "model_mismatch",
            default_model_id: "model-new",
            latest_prediction_job_id: "job-old",
            latest_prediction_model_id: "model-old",
            latest_prediction_dataset_revision_id: "revision-1",
            latest_prediction_status: "completed",
            active_prediction_job_id: null,
            active_prediction_status: null,
          },
          {
            member_id: "member-2",
            dataset_id: "dataset-2",
            expected_dataset_revision_id: "revision-2",
            status: "current",
            default_model_id: "model-new",
            latest_prediction_job_id: "job-current",
            latest_prediction_model_id: "model-new",
            latest_prediction_dataset_revision_id: "revision-2",
            latest_prediction_status: "completed",
            active_prediction_job_id: null,
            active_prediction_status: null,
          },
        ]),
      });
      return;
    }
    if (url.pathname.endsWith("/prediction-batches")) {
      if (request.method() === "POST") {
        submittedBody = request.postDataJSON();
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "batch-1",
            collection_id: "collection-1",
            collection_revision_id: "revision-1",
            model_id: "model-new",
            kind: "reconciliation",
            request_id: "request-1",
            status: "submitted",
            created_by: "user-e2e-1",
            created_at: "2026-08-15T00:00:00Z",
            updated_at: "2026-08-15T00:00:00Z",
            items: [],
          }),
        });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      }
      return;
    }
    if (url.pathname.endsWith("/membership-rules/rule-1/backfill-preview")) {
      backfillPreviewBody = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          as_of_utc: "2026-08-30T08:00:00Z",
          matched_count: 2,
          representative_records: [
            {
              record_key: "inspection-history-1",
              source_version: null,
              observed_at: "2026-08-20T08:00:00Z",
              display_name: "Historical inspection A",
              attributes: { layer_id: "M1", device: "DEVICE-A" },
            },
          ],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/membership-rules/rule-1/backfills")) {
      backfillRunBody = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "backfill-1",
          org_id: "org-e2e-1",
          collection_id: "collection-1",
          rule_id: "rule-1",
          rule_version_id: "rule-version-1",
          kind: "backfill",
          status: "completed",
          as_of_utc: "2026-08-30T08:00:00Z",
          range_start_utc: backfillRunBody.start_utc,
          range_end_utc: backfillRunBody.end_utc,
          timezone: backfillRunBody.timezone,
          parent_run_id: null,
          collection_revision_id: "revision-2",
          stats: {},
          error_detail: null,
          created_by: "user-e2e-1",
          created_at: "2026-08-30T08:00:00Z",
          completed_at: "2026-08-30T08:00:01Z",
          items: [],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/membership-rules")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "rule-1",
            org_id: "org-e2e-1",
            collection_id: "collection-1",
            name: "Metal layers",
            status: "active",
            active_version_id: "rule-version-1",
            activated_at: "2026-08-01T00:00:00Z",
            created_by: "user-e2e-1",
            created_at: "2026-08-01T00:00:00Z",
            updated_at: "2026-08-01T00:00:00Z",
            active_version: {
              id: "rule-version-1",
              rule_id: "rule-1",
              version: 1,
              connector_id: "connector-1",
              import_profile_version_id: "profile-1",
              condition: { combinator: "all", children: [] },
              created_by: "user-e2e-1",
              created_at: "2026-08-01T00:00:00Z",
            },
          },
        ]),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "collection-1",
        org_id: "org-e2e-1",
        name: "Production defects",
        description: "Daily inspection datasets",
        target_view_id: "patch_image_v1",
        target_view_contract: "sc.patch-image",
        target_schema_version: "1",
        duplicate_policy: "keep_all",
        missing_data_policy: "fail",
        definition_version: 1,
        default_model_id: "model-new",
        model_binding_version: 2,
        created_by: "user-e2e-1",
        created_at: "2026-08-15T00:00:00Z",
        updated_at: "2026-08-15T00:00:00Z",
      }),
    });
  });
  await authedPage.route("**/api/v1/datasets?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "dataset-1",
            name: "August line A",
            dataset_type: "image_sc",
            storage_mode: "file_shard_sparse",
            view_types: ["patch_image_v1"],
            task_spec: { task_type: "sc", label_space: ["ok", "defect"] },
            org_id: "org-e2e-1",
            is_public: false,
            created_at: "2026-08-15T00:00:00Z",
          },
          {
            id: "dataset-2",
            name: "August line B",
            dataset_type: "image_sc",
            storage_mode: "file_shard_sparse",
            view_types: ["patch_image_v1"],
            task_spec: { task_type: "sc", label_space: ["ok", "defect"] },
            org_id: "org-e2e-1",
            is_public: false,
            created_at: "2026-08-15T00:00:00Z",
          },
        ],
        total: 2,
      }),
    });
  });
  await authedPage.route("**/api/v1/datasets/dataset-*", async (route) => {
    const datasetId = new URL(route.request().url()).pathname.split("/").pop() ?? "";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: datasetId,
        name: datasetId === "dataset-1" ? "August line A" : "August line B",
        dataset_type: "image_sc",
        storage_mode: "file_shard_sparse",
        view_types: ["patch_image_v1"],
        task_spec: { task_type: "sc", label_space: ["0", "1"] },
        dataset_meta: {
          source_inspection_time:
            datasetId === "dataset-1" ? "2026-08-15T00:00:00Z" : "2026-08-16T00:00:00Z",
          source_wafer_key: datasetId === "dataset-1" ? 1 : 2,
          geometry: {
            wafer_radius_nm: 150000000,
            center_x: 0,
            center_y: 0,
            origin_x: 0,
            origin_y: 0,
            die_size_x: 10000,
            die_size_y: 10000,
          },
        },
        org_id: "org-e2e-1",
        is_public: false,
        created_at: "2026-08-15T00:00:00Z",
      }),
    });
  });
  await authedPage.route("**/api/v1/datasets/dataset-*/annotation-stats", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total_samples: 10,
        annotated_samples: 10,
        unlabeled_samples: 0,
        label_counts: { 0: 5, 1: 5 },
      }),
    });
  });
  const approvedModel = makeModel({
    id: "model-new",
    name: "Approved defect model",
    uri: "memory://model.pt",
    metadata: {},
    job_id: "training-1",
    trainer_name: "yolo-sc-v1",
    dataset_id: null,
    dataset_name: null,
  });
  await authedPage.route("**/api/v1/models**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/models/creators")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
      return;
    }
    if (url.pathname.endsWith("/models/model-new")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(approvedModel),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [approvedModel],
        total: 1,
      }),
    });
  });
  await authedPage.route("**/api/v1/source-connectors**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/source-connectors/providers")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            provider_id: "sc",
            display_name: "SC",
            fields: [],
            backfill_time_field: "inspection_time",
            max_condition_depth: 5,
            max_condition_nodes: 20,
          },
        ]),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "connector-1",
          org_id: "org-e2e-1",
          provider_id: "sc",
          name: "SC production",
          enabled: true,
          created_by: "user-e2e-1",
          created_at: "2026-08-01T00:00:00Z",
          updated_at: "2026-08-01T00:00:00Z",
        },
      ]),
    });
  });

  await authedPage.goto("/dataset-collections/collection-1");

  await authedPage
    .locator(".n-tabs-tab")
    .filter({ hasText: /^Models$/ })
    .click();
  await expect(authedPage.getByText("1 linked dataset uses a different model")).toBeVisible();
  await authedPage
    .locator(".n-tabs-tab")
    .filter({ hasText: /^Data & rules$/ })
    .click();
  await expect(authedPage.getByText("Dynamic membership", { exact: true })).toBeVisible();
  const ruleRow = authedPage.getByRole("row").filter({ hasText: "Metal layers" });
  const historicalImport = ruleRow.getByRole("button", { name: "Historical import" });
  await expect(historicalImport).toBeEnabled();
  await historicalImport.click();
  await expect(authedPage.getByTestId("membership-rule-backfill-modal")).toBeVisible();
  await expect(authedPage.getByTestId("backfill-start")).toBeVisible();
  await expect(authedPage.getByTestId("backfill-end")).toBeVisible();
  await expect(authedPage.getByTestId("backfill-timezone")).toBeVisible();
  await authedPage.getByTestId("backfill-preview").click();
  await expect.poll(() => backfillPreviewBody).not.toBeNull();
  await expect(authedPage.getByTestId("backfill-matched-count")).toHaveText("2");
  await expect(authedPage.getByText("Historical inspection A")).toBeVisible();
  await expect(authedPage.getByTestId("backfill-submit")).toBeDisabled();
  await authedPage.getByTestId("backfill-confirm-all").click();
  await expect(authedPage.getByTestId("backfill-submit")).toBeEnabled();
  await authedPage.getByTestId("backfill-submit").click();
  await expect.poll(() => backfillRunBody).not.toBeNull();
  expect(backfillRunBody).toEqual({
    start_utc: backfillPreviewBody?.start_utc,
    end_utc: backfillPreviewBody?.end_utc,
    timezone: backfillPreviewBody?.timezone,
  });
  await expect(authedPage.getByRole("button", { name: "View in Automations" })).toBeVisible();
  await authedPage.getByRole("button", { name: "Close", exact: true }).click();
  const mismatchRow = authedPage.getByRole("row").filter({ hasText: "August line A" });
  await mismatchRow.getByRole("checkbox").check();
  await authedPage.getByRole("button", { name: "Export selected (1)" }).click();
  await expect(authedPage.getByText("Export selected Collection records")).toBeVisible();
  await expect(
    authedPage.getByText("Parquet stays combined; KLARF creates one complete numbered file"),
  ).toBeVisible();
  await authedPage
    .getByTestId("sc-prediction-export")
    .getByRole("button", { name: "Close" })
    .click();
  await authedPage.getByRole("button", { name: "Predict selected (1)" }).click();
  await expect(authedPage.getByText("using Approved defect model and revision r1")).toBeVisible();
  await authedPage.getByRole("button", { name: "Start prediction" }).click();

  await expect
    .poll(() => submittedBody)
    .toMatchObject({
      revision_id: "revision-1",
      expected_default_model_id: "model-new",
      dataset_ids: ["dataset-1"],
    });

  await authedPage
    .locator(".n-tabs-tab")
    .filter({ hasText: /^Classify/ })
    .click();
  await expect(authedPage).toHaveURL(
    /\/dataset-collections\/collection-1\/revisions\/revision-1\/classify/,
  );
  const memberSelect = authedPage.getByTestId("sc-collection-member-select");
  await expect(memberSelect).toBeVisible();
  await expect(authedPage.getByTestId("sc-active-map-member-select")).toBeVisible();
  await memberSelect.click();
  await authedPage.locator(".n-base-select-option").filter({ hasText: "August line B" }).click();
  await expect.poll(() => new URL(authedPage.url()).searchParams.get("members")).toBe("member-1");
});
