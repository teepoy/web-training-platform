import { createJob } from "@/features/training/infrastructure/api";
import { updateLabelSpace } from "@/features/datasets/infrastructure/api";
import type { TrainingJob } from "@/types";

export async function startTrainingAction(
  datasetId: string,
  presetId: string,
): Promise<TrainingJob> {
  return createJob(datasetId, presetId);
}

export async function addLabelAction(
  datasetId: string,
  newLabel: string,
  currentLabels: string[],
): Promise<unknown> {
  if (currentLabels.includes(newLabel)) {
    throw new Error(`Label "${newLabel}" already exists`);
  }
  return updateLabelSpace(datasetId, [...currentLabels, newLabel]);
}
