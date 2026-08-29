/**
 * Playwright Custom Fixtures — test and expect extensions.
 *
 * ## Mode Contract
 * Tests are tagged `@mock` or `@live` and run in separate Playwright projects
 * (see `playwright.config.ts`). Each project only picks up tests with the
 * matching tag via `grep`.
 *
 * - **`@mock`** tests use `authedPage` (mock routes + pre-seeded localStorage)
 *   and `apiMocks` (bound T7 handler functions). No backend required.
 * - **`@live`** tests use `liveAuth` (JWT token cached per worker) and
 *   `seedClient` (orval-typed seed helpers). Real backend required.
 *
 * ## Available Fixtures
 * | Fixture     | Mode   | Scope   | Auto | Provides                                      |
 * |-------------|--------|---------|------|-----------------------------------------------|
 * | authedPage  | mock   | test    | yes  | Page with mockCoreApi routes + auth token      |
 * | apiMocks    | mock   | test    | no   | Bound T7 handler functions (page already wired)|
 * | liveAuth    | live   | worker  | no   | { token, user } from seedLogin (once/worker)   |
 * | seedClient  | live   | test    | no   | Typed seed helpers with current token          |
 * | testPrefix  | both   | test    | yes  | Unique `test-{workerIdx}-{slug}-{ts}` string   |
 *
 * ## Usage
 * ```ts
 * import { test, expect } from '../../fixtures';
 *
 * test('my test @mock', async ({ authedPage, apiMocks }) => {
 *   await apiMocks.datasets.mockListDatasets();
 *   await authedPage.goto('/datasets');
 *   await expect(authedPage).toHaveURL(/\/datasets/);
 * });
 * ```
 *
 * ## Cross-Mode Safety
 * - `apiMocks` throws if the test is NOT tagged `@mock`.
 * - `seedClient` throws if the test is NOT tagged `@live`.
 * - `authedPage` is a no-op pass-through in `@live` mode (no mock routes).
 */

import { test as base, expect } from "@playwright/test";
import type { Page, TestInfo } from "@playwright/test";

// ── T7 mock handlers ──────────────────────────────────────────────
import {
  // core
  mockCoreApi,
  mockOrganizations,
  mockExportFormats,
  mockHealth,
  mockDashboard,
  mockPlugins,
  // agent
  mockAgentUnavailable,
  // auth
  mockAuthLogin,
  mockAuthMe,
  // datasets
  mockListDatasets,
  mockGetDataset,
  mockListSamples,
  mockAnnotationStats,
  mockGetSample,
  mockSampleAnnotations,
  mockSamplePredictions,
  mockSampleSimilar,
  mockDatasetQuery,
  mockDatasetStatus,
  mockExportDownload,
  // training
  mockListTrainingJobs,
  mockGetJob,
  mockCreateTrainingJob,
  mockListTrainers,
  // prediction
  mockListPredictionJobs,
  mockGetPredictionJob,
  mockRunPrediction,
  mockListModels,
  mockTaskTracker,
  // schedules
  mockScheduleCapabilities,
  mockListSchedules,
  mockGetSchedule,
  mockCreateSchedule,
  mockDeleteSchedule,
  mockScheduleRuns,
  // preview
  mockCreatePreviewSession,
  mockGetPreviewSession,
  mockGetPreviewItems,
  mockPersistPreview,
  mockGetPersistStatus,
  mockExpiredPreviewSession,
  // sc
  mockScInspections,
  mockScInspectionSamples,
  mockScInspectionImageProfile,
  mockScDataset,
  mockScDataProvider,
  mockScViewSamples,
} from "../mocks/handlers";
import type { ScInspectionOverrides, ScDatasetOverrides } from "../mocks/handlers";
import type { CoreApiOverrides } from "../mocks/handlers";

// ── T6 seed layer ──────────────────────────────────────────────────
import { getSeedClient, seedLogin } from "../seed";
import type { SeedClient, SeedAuthResult } from "../seed";

// ── Types for handler signatures ──────────────────────────────────
import type { MockUser } from "../mocks/factories";
import type {
  Dataset,
  DatasetAnnotationStats,
  DatasetStatusResponse,
  SampleWithLabels,
  TrainingJob,
  PredictionJobResponse,
  ModelResponse,
  ScheduleResponse,
  OrgResponse,
} from "@/generated/orval/models";
import type { PreviewItem } from "@/shared/api/preview";

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════

/** Check whether the current test is tagged `@mock`. */
function isMockMode(testInfo: TestInfo): boolean {
  return testInfo.tags.includes("@mock");
}

/** Check whether the current test is tagged `@live`. */
function isLiveMode(testInfo: TestInfo): boolean {
  return testInfo.tags.includes("@live");
}

/** Slugify a test title for use in a prefix string. */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .substring(0, 40);
}

// ═══════════════════════════════════════════════════════════════════
// Live-auth cache (module-level, shared by liveAuth + seedClient)
// ═══════════════════════════════════════════════════════════════════

let _cachedAuth: SeedAuthResult | null = null;

/** Ensure a live backend login is performed exactly once per worker. */
async function ensureLiveAuth(): Promise<SeedAuthResult> {
  if (_cachedAuth) return _cachedAuth;

  const email = (process.env["PW_SEED_EMAIL"] as string | undefined) ?? "seed@example.com";
  const password = (process.env["PW_SEED_PASSWORD"] as string | undefined) ?? "seed1234";

  getSeedClient(); // patch fetch + configure orval (no token → login is unauthed)
  const auth = await seedLogin({ email, password });
  getSeedClient(auth.token); // reconfigure with the JWT

  _cachedAuth = auth;
  return auth;
}

// ═══════════════════════════════════════════════════════════════════
// Fixture type definitions
// ═══════════════════════════════════════════════════════════════════

/** Namespaced mock handler functions with page already bound. */
export interface ApiMocks {
  agent: {
    mockUnavailable: (detail?: string) => Promise<void>;
  };
  core: {
    mockCoreApi: (overrides?: CoreApiOverrides) => Promise<void>;
    mockOrganizations: (orgs?: OrgResponse[]) => Promise<void>;
    mockExportFormats: (formats?: { format_id: string }[]) => Promise<void>;
    mockHealth: () => Promise<void>;
    mockDashboard: () => Promise<void>;
    mockPlugins: () => Promise<void>;
  };
  auth: {
    mockAuthLogin: (token?: string) => Promise<void>;
    mockAuthMe: (user?: Partial<MockUser>) => Promise<void>;
  };
  datasets: {
    mockListDatasets: (datasets?: Dataset[]) => Promise<void>;
    mockGetDataset: (id: string, dataset?: Partial<Dataset>) => Promise<void>;
    mockListSamples: (datasetId: string, samples?: SampleWithLabels[]) => Promise<void>;
    mockAnnotationStats: (
      datasetId: string,
      stats?: Partial<DatasetAnnotationStats>,
    ) => Promise<void>;
    mockGetSample: (
      datasetId: string,
      sampleId: string,
      sample?: Partial<SampleWithLabels>,
    ) => Promise<void>;
    mockSampleAnnotations: (datasetId: string, sampleId: string) => Promise<void>;
    mockSamplePredictions: (datasetId: string, sampleId: string) => Promise<void>;
    mockSampleSimilar: (datasetId: string, sampleId: string) => Promise<void>;
    mockDatasetQuery: (datasetId: string) => Promise<void>;
    mockDatasetStatus: (
      datasetId: string,
      status?: Partial<DatasetStatusResponse>,
    ) => Promise<void>;
    mockExportDownload: () => Promise<void>;
  };
  training: {
    mockListTrainingJobs: (jobs?: TrainingJob[]) => Promise<void>;
    mockGetJob: (jobId: string, job?: Partial<TrainingJob>) => Promise<void>;
    mockCreateTrainingJob: () => Promise<void>;
    mockListTrainers: (trainers?: Record<string, unknown>[]) => Promise<void>;
  };
  prediction: {
    mockListPredictionJobs: (jobs?: PredictionJobResponse[]) => Promise<void>;
    mockGetPredictionJob: (jobId: string, job?: Partial<PredictionJobResponse>) => Promise<void>;
    mockRunPrediction: (datasetId: string, modelId: string, jobId?: string) => Promise<void>;
    mockListModels: (models?: ModelResponse[]) => Promise<void>;
    mockTaskTracker: (taskId: string) => Promise<void>;
  };
  schedules: {
    mockScheduleCapabilities: () => Promise<void>;
    mockListSchedules: (schedules?: ScheduleResponse[]) => Promise<void>;
    mockGetSchedule: (scheduleId: string, schedule?: Partial<ScheduleResponse>) => Promise<void>;
    mockCreateSchedule: () => Promise<void>;
    mockDeleteSchedule: (scheduleId: string) => Promise<void>;
    mockScheduleRuns: (scheduleId: string) => Promise<void>;
  };
  preview: {
    mockCreatePreviewSession: (sessionId: string, collectionRef: string) => Promise<void>;
    mockGetPreviewSession: (sessionId: string, collectionRef?: string) => Promise<void>;
    mockGetPreviewItems: (sessionId: string, items?: PreviewItem[]) => Promise<void>;
    mockPersistPreview: (sessionId: string, datasetId: string) => Promise<void>;
    mockGetPersistStatus: (sessionId: string, datasetId: string) => Promise<void>;
    mockExpiredPreviewSession: (sessionId: string) => Promise<void>;
  };
  sc: {
    mockScInspections: (overrides?: ScInspectionOverrides) => Promise<void>;
    mockScInspectionSamples: () => Promise<void>;
    mockScDataset: (datasetId: string, overrides?: ScDatasetOverrides) => Promise<void>;
    mockScViewSamples: (
      datasetId: string,
      viewType?: string,
      overrides?: { total?: number },
    ) => Promise<void>;
  };
}

/** Test-scoped fixtures (scope: 'test') — fresh per test. */
export interface TestFixtures {
  authedPage: Page;
  apiMocks: ApiMocks;
  seedClient: SeedClient;
  testPrefix: string;
}

/** Worker-scoped fixtures (scope: 'worker') — cached per worker. */
export interface WorkerFixtures {
  liveAuth: SeedAuthResult;
}

// ═══════════════════════════════════════════════════════════════════
// Extended test
// ═══════════════════════════════════════════════════════════════════

export const test = base.extend<TestFixtures, WorkerFixtures>({
  /**
   * Mock-mode: sets up `mockCoreApi` routes on the page and pre-seeds
   * localStorage with the mock auth token so the app starts authenticated.
   *
   * Live-mode: pass-through (no mock routes). The page is still available
   * but without any mocked API interceptors.
   *
   * Auto-fixture — available in every test without explicit declaration.
   */
  authedPage: async ({ page }, use, testInfo) => {
    if (isMockMode(testInfo)) {
      await mockCoreApi(page);
      await mockListTrainers(page);
      await mockScDataProvider(page, "*");
      await mockScInspectionImageProfile(page);
      // Use addInitScript so the token is set before any app code runs on navigation.
      // Direct page.evaluate fails because about:blank has no localStorage access.
      await page.addInitScript(() => {
        localStorage.setItem("auth_token", "e2e-token");
      });
    }
    await use(page);
  },

  /**
   * Live-mode only. Authenticates against the real backend once per worker
   * and caches the JWT token + user object. Subsequent tests reuse the
   * same token without re-logging in.
   *
   * Scope: worker — the login is performed once and the token is reused
   * across all tests in the worker.
   */
  liveAuth: [
    async ({}, use) => {
      const auth = await ensureLiveAuth();
      await use(auth);
      // No explicit logout — token expires naturally.
    },
    { scope: "worker" },
  ],

  /**
   * Mock-mode only. Returns an object where every T7 handler function is
   * bound to the current page, so specs call e.g.
   * `apiMocks.datasets.mockListDatasets(myData)` without passing `page`.
   *
   * Throws if accessed in a `@live` test.
   */
  apiMocks: async ({ page }, use, testInfo) => {
    if (!isMockMode(testInfo)) {
      throw new Error(
        "apiMocks is a mock-only fixture — accessed in a @live test. " +
          "Tag your spec with @mock or use seedClient instead.",
      );
    }

    const bound: ApiMocks = {
      agent: {
        mockUnavailable: (detail) => mockAgentUnavailable(page, detail),
      },
      core: {
        mockCoreApi: (overrides) => mockCoreApi(page, overrides),
        mockOrganizations: (orgs) => mockOrganizations(page, orgs),
        mockExportFormats: (formats) => mockExportFormats(page, formats),
        mockHealth: () => mockHealth(page),
        mockDashboard: () => mockDashboard(page),
        mockPlugins: () => mockPlugins(page),
      },
      auth: {
        mockAuthLogin: (token) => mockAuthLogin(page, token),
        mockAuthMe: (user) => mockAuthMe(page, user),
      },
      datasets: {
        mockListDatasets: (datasets) => mockListDatasets(page, datasets),
        mockGetDataset: (id, dataset) => mockGetDataset(page, id, dataset),
        mockListSamples: (datasetId, samples) => mockListSamples(page, datasetId, samples),
        mockAnnotationStats: (datasetId, stats) => mockAnnotationStats(page, datasetId, stats),
        mockGetSample: (datasetId, sampleId, sample) =>
          mockGetSample(page, datasetId, sampleId, sample),
        mockSampleAnnotations: (datasetId, sampleId) =>
          mockSampleAnnotations(page, datasetId, sampleId),
        mockSamplePredictions: (datasetId, sampleId) =>
          mockSamplePredictions(page, datasetId, sampleId),
        mockSampleSimilar: (datasetId, sampleId) => mockSampleSimilar(page, datasetId, sampleId),
        mockDatasetQuery: (datasetId) => mockDatasetQuery(page, datasetId),
        mockDatasetStatus: (datasetId, status) => mockDatasetStatus(page, datasetId, status),
        mockExportDownload: () => mockExportDownload(page),
      },
      training: {
        mockListTrainingJobs: (jobs) => mockListTrainingJobs(page, jobs),
        mockGetJob: (jobId, job) => mockGetJob(page, jobId, job),
        mockCreateTrainingJob: () => mockCreateTrainingJob(page),
        mockListTrainers: (trainers) => mockListTrainers(page, trainers),
      },
      prediction: {
        mockListPredictionJobs: (jobs) => mockListPredictionJobs(page, jobs),
        mockGetPredictionJob: (jobId, job) => mockGetPredictionJob(page, jobId, job),
        mockRunPrediction: (datasetId, modelId, jobId) =>
          mockRunPrediction(page, datasetId, modelId, jobId),
        mockListModels: (models) => mockListModels(page, models),
        mockTaskTracker: (taskId) => mockTaskTracker(page, taskId),
      },
      schedules: {
        mockScheduleCapabilities: () => mockScheduleCapabilities(page),
        mockListSchedules: (schedules) => mockListSchedules(page, schedules),
        mockGetSchedule: (scheduleId, schedule) => mockGetSchedule(page, scheduleId, schedule),
        mockCreateSchedule: () => mockCreateSchedule(page),
        mockDeleteSchedule: (scheduleId) => mockDeleteSchedule(page, scheduleId),
        mockScheduleRuns: (scheduleId) => mockScheduleRuns(page, scheduleId),
      },
      preview: {
        mockCreatePreviewSession: (sessionId, collectionRef) =>
          mockCreatePreviewSession(page, sessionId, collectionRef),
        mockGetPreviewSession: (sessionId, collectionRef) =>
          mockGetPreviewSession(page, sessionId, collectionRef),
        mockGetPreviewItems: (sessionId, items) => mockGetPreviewItems(page, sessionId, items),
        mockPersistPreview: (sessionId, datasetId) =>
          mockPersistPreview(page, sessionId, datasetId),
        mockGetPersistStatus: (sessionId, datasetId) =>
          mockGetPersistStatus(page, sessionId, datasetId),
        mockExpiredPreviewSession: (sessionId) => mockExpiredPreviewSession(page, sessionId),
      },
      sc: {
        mockScInspections: (overrides) => mockScInspections(page, overrides),
        mockScInspectionSamples: () => mockScInspectionSamples(page),
        mockScDataset: (datasetId, overrides) => mockScDataset(page, datasetId, overrides),
        mockScViewSamples: (datasetId, viewType, overrides) =>
          mockScViewSamples(page, datasetId, viewType, overrides),
      },
    };

    await use(bound);
  },

  /**
   * Live-mode only. Returns a configured `SeedClient` with the current
   * test's JWT token, enabling typed seed helpers (createDataset,
   * addSamples, etc.).
   *
   * Throws if accessed in a `@mock` test.
   */
  seedClient: async ({}, use, testInfo) => {
    if (!isLiveMode(testInfo)) {
      throw new Error(
        "seedClient is a live-only fixture — accessed in a @mock test. " +
          "Tag your spec with @live or use apiMocks instead.",
      );
    }

    const auth = await ensureLiveAuth();
    await use(getSeedClient(auth.token));
  },

  /**
   * Unique per-test prefix string, suitable for scoping created resources
   * (datasets, jobs, etc.) so cleanup can find and delete them by prefix.
   *
   * Format: `test-{workerIndex}-{slugifiedTitle}-{timestamp}`
   *
   * Auto-fixture — available in every test without explicit declaration.
   */
  testPrefix: [
    async ({}, use, testInfo) => {
      const slug = slugify(testInfo.title);
      const prefix = `test-${testInfo.workerIndex}-${slug}-${Date.now()}`;
      await use(prefix);
    },
    { auto: true },
  ],
});

export { expect };
