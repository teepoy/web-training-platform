import type { ConsoleMessage } from "@playwright/test";

import { expect, test } from "../../fixtures";
import { AgentChatPage } from "../../pages/agent/AgentChatPage";
import { DatasetDetailPage } from "../../pages/datasets/DatasetDetailPage";
import { addSamples, cleanupTestArtifacts, createDataset } from "../../seed";
import { E2E_TIMEOUTS } from "../../timeouts";

test("global agent reports route context and backend errors @mock", async ({
  authedPage,
  apiMocks,
}) => {
  const datasetId = "agent-qa-mock-dataset";
  const backendError = "Mock Agent backend is not configured";

  await apiMocks.datasets.mockGetDataset(datasetId);
  await apiMocks.datasets.mockListSamples(datasetId, []);
  await apiMocks.datasets.mockAnnotationStats(datasetId, {
    total_samples: 0,
    annotated_samples: 0,
    unlabeled_samples: 0,
    label_counts: {},
  });
  await apiMocks.datasets.mockDatasetStatus(datasetId, {
    allow_train: false,
    train_disabled_reason: "no_samples",
    active_class_count: 0,
    annotated_samples: 0,
    total_samples: 0,
  });
  await apiMocks.training.mockListTrainingJobs([]);
  await apiMocks.training.mockListTrainers([]);
  await apiMocks.agent.mockUnavailable(backendError);

  const detailPage = new DatasetDetailPage(authedPage);
  await detailPage.gotoDetail(datasetId);
  await detailPage.waitForLoaded();

  const agentPage = new AgentChatPage(authedPage);
  await agentPage.openDrawer();
  await expect(agentPage.getHeaderTitle()).toHaveText("Agent Chat");
  await expect(agentPage.getEmptyState()).toBeVisible();

  const requestPromise = authedPage.waitForRequest(
    (request) =>
      request.method() === "POST" && new URL(request.url()).pathname === "/api/v1/agent/chat",
  );
  await agentPage.sendMessage("Check the current dataset without changing it.");

  const request = await requestPromise;
  const requestBody = request.postDataJSON() as {
    message?: string;
    context?: { page?: string; dataset_id?: string };
  };
  expect(requestBody.message).toBe("Check the current dataset without changing it.");
  expect(requestBody.context).toEqual({
    page: `/datasets/${datasetId}`,
    dataset_id: datasetId,
  });
  await expect(agentPage.getUserMessages()).toHaveCount(1);
  await expect(agentPage.getAssistantMessages()).toContainText(`Error: ${backendError}`);
  await expect(agentPage.getLoadingIndicator()).toBeHidden();
});

test.describe("Agent QA live", () => {
  test.setTimeout(E2E_TIMEOUTS.test.agent);

  let datasetId: string | undefined;

  test.beforeEach(async ({ page, liveAuth, testPrefix }) => {
    await page.addInitScript((token) => {
      localStorage.setItem("auth_token", token);
    }, liveAuth.token);

    const dataset = await createDataset({
      name: `${testPrefix}-agent-qa`,
      dataset_type: "image_classification",
      task_spec: { task_type: "classification", label_space: ["cat", "dog"] },
    });
    datasetId = dataset.id!;

    await addSamples(datasetId, {
      items: [
        {
          image_uris: ["memory://e2e-agent-qa.jpg"],
          metadata: { source: "e2e-live-agent-qa" },
          label: null,
        },
      ],
    });
  });

  test.afterEach(async ({ testPrefix }) => {
    await cleanupTestArtifacts(testPrefix);
  });

  test("global agent entry and backend readiness fail explicitly @live", async ({ page }) => {
    const pageErrors: Error[] = [];
    const severeConsoleMessages: ConsoleMessage[] = [];
    page.on("pageerror", (error) => pageErrors.push(error));
    page.on("console", (message) => {
      if (message.type() === "error") severeConsoleMessages.push(message);
    });

    const detailPage = new DatasetDetailPage(page);
    await detailPage.gotoDetail(datasetId!);
    await detailPage.waitForLoaded();

    const agentPage = new AgentChatPage(page);
    await agentPage.openDrawer();
    await expect(agentPage.getHeaderTitle()).toHaveText("Agent Chat");
    await expect(agentPage.getEmptyState()).toBeVisible();

    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/agent/chat",
      { timeout: E2E_TIMEOUTS.operation.agent },
    );
    await agentPage.sendMessage("Run a read-only QA check for the current dataset context.");

    const response = await responsePromise;
    const requestBody = response.request().postDataJSON() as {
      message?: string;
      context?: { page?: string; dataset_id?: string };
    };
    expect(requestBody.message).toContain("read-only QA check");
    expect(requestBody.context?.dataset_id).toBe(datasetId);
    expect(requestBody.context?.page).toBe(`/datasets/${datasetId}`);
    await expect(agentPage.getUserMessages()).toHaveCount(1);

    if (response.status() === 503) {
      await expect(agentPage.getAssistantMessages()).toContainText("LLM not configured", {
        timeout: E2E_TIMEOUTS.expect,
      });
    } else {
      expect(response.status()).toBe(200);
      expect(response.headers()["content-type"]).toContain("text/event-stream");
      await expect(agentPage.getAnyResponse().first()).toBeVisible({
        timeout: E2E_TIMEOUTS.operation.agent,
      });
    }

    await expect(agentPage.getLoadingIndicator()).toBeHidden({
      timeout: E2E_TIMEOUTS.operation.agent,
    });
    expect(pageErrors).toEqual([]);
    expect(
      severeConsoleMessages.filter(
        (message) => !message.text().includes("503 (Service Unavailable)"),
      ),
    ).toEqual([]);
  });
});
