import type { Page } from "@playwright/test";
import type { Dataset, OrgResponse } from "@/generated/orval/models";
import type { MockUser } from "../factories";
import { MOCK_ORG_ID } from "../constants";
import { makeFlowerDataset, makeUser } from "../factories";
import { mockAuthLogin, mockAuthMe } from "./auth";
import { mockListDatasets } from "./datasets";

export interface CoreApiOverrides {
  user?: Partial<MockUser>;
  datasets?: Dataset[];
  orgs?: OrgResponse[];
}

export async function mockOrganizations(page: Page, orgs?: OrgResponse[]): Promise<void> {
  const body = orgs ?? [
    {
      id: MOCK_ORG_ID,
      name: "E2E Org",
      slug: "e2e-org",
      created_at: "2026-01-01T00:00:00Z",
    },
  ];
  await page.route("**/api/v1/organizations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockExportFormats(
  page: Page,
  formats?: { format_id: string }[],
): Promise<void> {
  const body = formats ?? [{ format_id: "annotation-version-full-context-v1" }];
  await page.route("**/api/v1/export-formats", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockHealth(page: Page): Promise<void> {
  await page.route("**/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok" }),
    });
  });
}

export async function mockDashboard(page: Page): Promise<void> {
  await page.route("**/api/v1/dashboard", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
}

export async function mockCollectionCreators(page: Page): Promise<void> {
  await page.route("**/api/v1/dataset-collections/creators", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

export async function mockPlugins(page: Page): Promise<void> {
  await page.route("**/api/v1/plugins/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

/**
 * Combined core mock that sets up auth, organization, and dataset list
 * defaults — replacing the per-spec `mockCoreApi` function found in every
 * old e2e file.  Accept an optional overrides bag so individual specs
 * can tweak the default user / dataset list / org list without rebuilding
 * the entire route set.
 */
export async function mockCoreApi(page: Page, overrides?: CoreApiOverrides): Promise<void> {
  await mockHealth(page);
  await mockAuthLogin(page);
  await mockAuthMe(page, overrides?.user ?? {});
  await mockOrganizations(page, overrides?.orgs);
  await mockCollectionCreators(page);
  await mockListDatasets(page, overrides?.datasets);
}
