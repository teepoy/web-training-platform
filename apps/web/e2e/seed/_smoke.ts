/**
 * End-to-end smoke script for the generated API client.
 *
 * Flow: login → create dataset → add sample → delete → cleanup.
 *
 * Usage:
 *   pnpm --filter web exec tsx tests/seed/_smoke.ts
 *
 * Prerequisites:
 *   make up          (backend + worker must be running)
 */
import {
  getSeedClient,
  seedLogin,
  createDataset,
  addSamples,
  deleteDataset,
  cleanupTestArtifacts,
} from "./index";
import type {
  LoginRequest,
  CreateDatasetRequest,
  BulkCreateSampleRequest,
  BulkCreateSampleItem,
} from "../../src/generated/orval/models";

const EMAIL = process.env["PW_USER_EMAIL"] as string | undefined;
const PASSWORD = process.env["PW_USER_PASSWORD"] as string | undefined;

async function main(): Promise<void> {
  if (!EMAIL || !PASSWORD) {
    throw new Error("PW_USER_EMAIL and PW_USER_PASSWORD are required");
  }
  // 1. Configure seed client (no token → login is unauthenticated)
  getSeedClient();

  // 2. Login
  const creds: LoginRequest = { email: EMAIL, password: PASSWORD };
  const { token, user } = await seedLogin(creds);
  console.log(`LOGIN OK user=${user.email} id=${user.id}`);

  // 3. Reconfigure seed client with the JWT
  getSeedClient(token);

  // 4. Create a test dataset
  const dsName = `_smoke_test_${Date.now()}`;
  const datasetReq: CreateDatasetRequest = { name: dsName };
  const dataset = await createDataset(datasetReq);
  const datasetId = dataset.id!;
  console.log(`DATASET CREATED id=${datasetId}`);

  // 5. Add a sample
  const sampleItem: BulkCreateSampleItem = {
    image_uris: ["https://example.com/test.png"],
  };
  const sampleReq: BulkCreateSampleRequest = { items: [sampleItem] };
  const sampleResult = await addSamples(datasetId, sampleReq);
  console.log(`SAMPLE ADDED imported=${sampleResult.imported}`);

  // 6. Delete the dataset
  await deleteDataset(datasetId);
  console.log("DATASET DELETED");

  // 7. Clean up any leftover smoke datasets from previous runs
  await cleanupTestArtifacts("_smoke_");
  console.log("DONE");
}

main().catch((err: unknown) => {
  console.error("SMOKE FAILED:", (err as Error)?.message ?? String(err));
  process.exit(1);
});
