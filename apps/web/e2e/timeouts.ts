function timeoutFromEnv(name: string, fallbackMs: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw === "") return fallbackMs;

  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer number of milliseconds; received ${raw}`);
  }
  return value;
}

/**
 * Central E2E timeout policy.
 *
 * UI waits stay short so regressions fail quickly. Only tests that launch
 * known long-running backend work opt into an operation-specific test budget.
 * Every value can be raised explicitly for a slower acceptance environment.
 */
export const E2E_TIMEOUTS = Object.freeze({
  expect: timeoutFromEnv("PLAYWRIGHT_EXPECT_TIMEOUT_MS", 10_000),
  action: timeoutFromEnv("PLAYWRIGHT_ACTION_TIMEOUT_MS", 15_000),
  navigation: timeoutFromEnv("PLAYWRIGHT_NAVIGATION_TIMEOUT_MS", 30_000),
  webServer: timeoutFromEnv("PLAYWRIGHT_WEB_SERVER_TIMEOUT_MS", 120_000),
  test: Object.freeze({
    mock: timeoutFromEnv("PLAYWRIGHT_MOCK_TEST_TIMEOUT_MS", 30_000),
    live: timeoutFromEnv("PLAYWRIGHT_LIVE_TEST_TIMEOUT_MS", 120_000),
    agent: timeoutFromEnv("PLAYWRIGHT_AGENT_TEST_TIMEOUT_MS", 300_000),
    scImport: timeoutFromEnv("PLAYWRIGHT_SC_IMPORT_TEST_TIMEOUT_MS", 600_000),
    scAnnotation: timeoutFromEnv("PLAYWRIGHT_SC_ANNOTATION_TEST_TIMEOUT_MS", 600_000),
    scTraining: timeoutFromEnv("PLAYWRIGHT_SC_TRAINING_TEST_TIMEOUT_MS", 1_800_000),
    scPrediction: timeoutFromEnv("PLAYWRIGHT_SC_PREDICTION_TEST_TIMEOUT_MS", 2_700_000),
    scFullWorkflow: timeoutFromEnv("PLAYWRIGHT_SC_FULL_WORKFLOW_TEST_TIMEOUT_MS", 2_700_000),
  }),
  operation: Object.freeze({
    jobCancellation: timeoutFromEnv("PLAYWRIGHT_JOB_CANCELLATION_TIMEOUT_MS", 60_000),
    scImport: timeoutFromEnv("PLAYWRIGHT_SC_IMPORT_TIMEOUT_MS", 600_000),
    scDataLoad: timeoutFromEnv("PLAYWRIGHT_SC_DATA_LOAD_TIMEOUT_MS", 180_000),
    training: timeoutFromEnv("PLAYWRIGHT_TRAINING_TIMEOUT_MS", 900_000),
    prediction: timeoutFromEnv("PLAYWRIGHT_PREDICTION_TIMEOUT_MS", 900_000),
    agent: timeoutFromEnv("PLAYWRIGHT_AGENT_TIMEOUT_MS", 240_000),
  }),
  pollInterval: timeoutFromEnv("PLAYWRIGHT_POLL_INTERVAL_MS", 3_000),
});
