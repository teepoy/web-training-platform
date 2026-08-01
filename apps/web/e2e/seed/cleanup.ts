/**
 * Cleanup helpers — best-effort deletion of test artifacts.
 */
import type { Dataset } from "../../src/generated/orval/models";
import {
  listDatasetsApiV1DatasetsGet,
  deleteDatasetApiV1DatasetsDatasetIdDelete,
} from "../../src/generated/orval/endpoints/api";

/**
 * Delete all datasets whose name starts with the given prefix.
 *
 * Best-effort: individual delete failures are logged and skipped so
 * one broken dataset does not prevent cleanup of the rest.
 *
 * IMPORTANT: call {@link getSeedClient} (from `./client`) with a valid
 * token BEFORE calling this.
 */
export async function cleanupTestArtifacts(prefix: string): Promise<void> {
  try {
    const page = await listDatasetsApiV1DatasetsGet();
    const datasets: Dataset[] = page.items;

    for (const ds of datasets) {
      if (ds.name?.startsWith(prefix)) {
        const id = ds.id;
        if (!id) continue;
        try {
          await deleteDatasetApiV1DatasetsDatasetIdDelete(id);
          console.log(`[cleanup] Deleted dataset ${id} (${ds.name})`);
        } catch (e: unknown) {
          console.warn(
            `[cleanup] Failed to delete dataset ${id}: ${(e as Error)?.message ?? String(e)}`,
          );
        }
      }
    }
  } catch (e: unknown) {
    console.warn(`[cleanup] Failed to list datasets: ${(e as Error)?.message ?? String(e)}`);
  }
}
