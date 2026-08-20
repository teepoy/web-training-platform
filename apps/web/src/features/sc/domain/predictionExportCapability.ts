import type { Dataset } from "@/generated/orval/models";

type ScPredictionExportCandidate = Pick<Dataset, "dataset_type" | "storage_mode" | "task_spec">;

export function supportsScPredictionExport(dataset: ScPredictionExportCandidate | null): boolean {
  return (
    dataset?.dataset_type === "image_sc" &&
    dataset.task_spec?.task_type === "sc" &&
    dataset.storage_mode === "file_shard_sparse"
  );
}
