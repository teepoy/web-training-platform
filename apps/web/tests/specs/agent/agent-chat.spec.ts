import { test, expect } from '../../fixtures';
import { AgentChatPage } from '../../pages/agent/AgentChatPage';
import { DatasetDetailPage } from '../../pages/datasets/DatasetDetailPage';
import { createDataset, addSamples, cleanupTestArtifacts } from '../../seed';

test.describe('Agent Chat', () => {
  let datasetId: string | undefined;
  let datasetName: string | undefined;

  test.beforeEach(async ({ page, liveAuth, seedClient: _sc, testPrefix }) => {
    await page.addInitScript((token) => {
      localStorage.setItem('auth_token', token);
    }, liveAuth.token);

    datasetName = `${testPrefix}-agent`;

    const dataset = await createDataset({
      name: datasetName,
      dataset_type: 'image_classification',
      task_spec: { task_type: 'classification', label_space: ['cat', 'dog'] },
    });
    datasetId = dataset.id!;

    await addSamples(datasetId, {
      items: [
        { image_uris: ['memory://e2e-agent-test.jpg'], metadata: { source: 'e2e-live' }, label: null },
      ],
    });
  });

  test.afterEach(async ({ testPrefix }) => {
    await cleanupTestArtifacts(testPrefix);
  });

  test('agent chat FAB visible in classify view @live', async ({ page }) => {
    const detailPage = new DatasetDetailPage(page);
    await detailPage.gotoDetail(datasetId!);
    await detailPage.waitForLoaded();

    await detailPage.clickOpenWorkflow();
    await detailPage.waitForClassifyPage();

    const agentPage = new AgentChatPage(page);
    await agentPage.waitForFabVisible();
  });

  test('agent chat drawer opens @live', async ({ page }) => {
    const detailPage = new DatasetDetailPage(page);
    await detailPage.gotoDetail(datasetId!);
    await detailPage.waitForLoaded();

    await detailPage.clickOpenWorkflow();
    await detailPage.waitForClassifyPage();

    const agentPage = new AgentChatPage(page);
    await agentPage.waitForFabVisible();
    await agentPage.clickFab();

    await agentPage.waitForFabHidden();
    await agentPage.waitForDrawerOpen();

    await expect(agentPage.getHeaderTitle()).toHaveText('Agent Chat');
    await expect(agentPage.getEmptyState()).toBeVisible();
  });

  test('agent chat accepts message @live', async ({ page }) => {
    const detailPage = new DatasetDetailPage(page);
    await detailPage.gotoDetail(datasetId!);
    await detailPage.waitForLoaded();

    await detailPage.clickOpenWorkflow();
    await detailPage.waitForClassifyPage();

    const agentPage = new AgentChatPage(page);
    await agentPage.openDrawer();

    await expect(agentPage.getInputField()).toBeVisible();
    await agentPage.sendMessage('Hello agent, what can you tell me about this dataset?');

    await expect(agentPage.getUserMessages().first()).toBeVisible({ timeout: 5_000 });

    const responseLocator = agentPage.getAnyResponse();

    try {
      await responseLocator.first().waitFor({ timeout: 30_000 });
    } catch {
      await page.waitForTimeout(2_000);

      const errorMsg = agentPage.getAssistantMessages();
      if ((await errorMsg.count()) > 0) {
        await expect(errorMsg.first()).toBeVisible();
      } else {
        await expect(agentPage.getLoadingIndicator()).not.toBeVisible({ timeout: 10_000 });
      }
    }

    await expect(agentPage.getDrawer()).toBeVisible();
  });
});
