import { expect, test } from "../../fixtures";

test("reruns only selected collection datasets with the pinned model @mock", async ({
  authedPage,
}) => {
  let submittedBody: unknown;
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
    if (url.pathname.endsWith("/snapshot-update-status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          snapshot_id: "snapshot-1",
          snapshot_revision_number: 1,
          update_available: false,
          outdated_member_count: 0,
          members: [],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/revisions")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "snapshot-1",
            collection_id: "collection-1",
            revision_number: 1,
            definition_version: 1,
            definition_hash: "hash-1",
            target_view_id: "patch_image_v1",
            target_view_contract: "sc.patch-image",
            target_schema_version: "1",
            status: "ready",
            source_snapshot: [
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
            row_count: 20,
            label_counts: {},
            manifest_uri: null,
            provenance_uri: null,
            trigger_kind: "manual",
            trigger_ref: null,
            created_by: "user-e2e-1",
            created_at: "2026-08-15T00:00:00Z",
            error_code: null,
            error_detail: null,
            manifest_format: "collection-composite-observed.v1",
            source_resolution: "observed",
            reproducibility_capability: false,
          },
        ]),
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
            collection_revision_id: "snapshot-1",
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
    if (url.pathname.endsWith("/membership-rules")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
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
  await authedPage.route("**/api/v1/models?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "model-new",
            name: "Approved defect model",
            uri: "memory://model.pt",
            kind: "model",
            metadata: {},
            job_id: "training-1",
            trainer_name: "yolo-sc-v1",
          },
        ],
        total: 1,
      }),
    });
  });
  await authedPage.route("**/api/v1/source-connectors**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
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
  await expect(authedPage.getByText("using Approved defect model and snapshot r1")).toBeVisible();
  await authedPage.getByRole("button", { name: "Start prediction" }).click();

  await expect
    .poll(() => submittedBody)
    .toMatchObject({
      snapshot_id: "snapshot-1",
      expected_default_model_id: "model-new",
      dataset_ids: ["dataset-1"],
    });

  await authedPage
    .locator(".n-tabs-tab")
    .filter({ hasText: /^Classify/ })
    .click();
  await expect(authedPage).toHaveURL(
    /\/dataset-collections\/collection-1\/classify\/dataset-1\?revisionId=snapshot-1$/,
  );
});

test("shows and explicitly refreshes an outdated Collection Snapshot @mock", async ({
  authedPage,
}) => {
  let refreshBody: unknown;
  let refreshed = false;
  const snapshot = (revisionNumber: number, datasetRevisionId: string) => ({
    id: `snapshot-${revisionNumber}`,
    collection_id: "collection-1",
    revision_number: revisionNumber,
    definition_version: 1,
    definition_hash: `hash-${revisionNumber}`,
    target_view_id: "patch_image_v1",
    target_view_contract: "sc.patch-image",
    target_schema_version: "1",
    status: "ready",
    source_snapshot: [
      {
        member_id: "member-1",
        source_dataset_id: "dataset-1",
        dataset_revision_id: datasetRevisionId,
        dataset_revision_number: revisionNumber,
      },
    ],
    row_count: null,
    label_counts: {},
    manifest_uri: `memory://snapshot-${revisionNumber}.json`,
    provenance_uri: null,
    trigger_kind: revisionNumber === 1 ? "manual" : "dataset_revision_refresh",
    trigger_ref: revisionNumber === 1 ? null : "snapshot-1",
    created_by: "user-e2e-1",
    created_at: "2026-08-15T00:00:00Z",
    error_code: null,
    error_detail: null,
    manifest_format: "collection-composite-observed.v1",
    source_resolution: "observed",
    reproducibility_capability: false,
  });

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
        ]),
      });
      return;
    }
    if (url.pathname.endsWith("/snapshot-update-status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          snapshot_id: refreshed ? "snapshot-2" : "snapshot-1",
          snapshot_revision_number: refreshed ? 2 : 1,
          update_available: !refreshed,
          outdated_member_count: refreshed ? 0 : 1,
          members: [
            {
              member_id: "member-1",
              dataset_id: "dataset-1",
              observed_dataset_revision_id: refreshed ? "dataset-revision-2" : "dataset-revision-1",
              observed_dataset_revision_number: refreshed ? 2 : 1,
              current_dataset_revision_id: "dataset-revision-2",
              current_dataset_revision_number: 2,
              update_available: !refreshed,
            },
          ],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/refresh-snapshot")) {
      refreshBody = request.postDataJSON();
      refreshed = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          outcome: "refreshed",
          snapshot: snapshot(2, "dataset-revision-2"),
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/revisions")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          refreshed
            ? [snapshot(2, "dataset-revision-2"), snapshot(1, "dataset-revision-1")]
            : [snapshot(1, "dataset-revision-1")],
        ),
      });
      return;
    }
    if (
      url.pathname.endsWith("/prediction-coverage") ||
      url.pathname.endsWith("/prediction-batches")
    ) {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    if (url.pathname.endsWith("/membership-rules")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
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
        default_model_id: null,
        model_binding_version: 0,
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
            dataset_type: "sc_patch",
            view_types: ["patch_image_v1"],
            task_spec: { task_type: "classification", label_space: ["ok", "defect"] },
            org_id: "org-e2e-1",
            is_public: false,
            created_at: "2026-08-15T00:00:00Z",
          },
        ],
        total: 1,
      }),
    });
  });
  await authedPage.route("**/api/v1/models?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], total: 0 }),
    });
  });
  await authedPage.route("**/api/v1/source-connectors**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await authedPage.goto("/dataset-collections/collection-1");

  await expect(authedPage.getByText("Update available")).toBeVisible();
  await expect(authedPage.getByText("1 linked Dataset has newer change numbers")).toBeVisible();
  await authedPage.getByTestId("refresh-collection-snapshot").click();
  await expect.poll(() => refreshBody).toEqual({ expected_definition_version: 1 });
  await expect(authedPage.getByText("Update available")).toBeHidden();
  await expect(
    authedPage.getByText("Snapshot #2 now records the latest Dataset changes"),
  ).toBeVisible();
});
