import { defineStore } from "pinia";

export const useScReclassifyStore = defineStore("scReclassify", {
  state: () => ({
    selectedDefectIdsByDataset: {} as Record<string, string[]>,
    samplingDefectIdsByDataset: {} as Record<string, string[]>,
  }),
  actions: {
    setSelectedDefectIds(datasetId: string, defectIds: Iterable<string>): void {
      this.selectedDefectIdsByDataset[datasetId] = [...new Set(defectIds)];
    },
    clearSelectedDefectIds(datasetId: string): void {
      delete this.selectedDefectIdsByDataset[datasetId];
    },
    setSamplingDefectIds(datasetId: string, defectIds: Iterable<string>): void {
      this.samplingDefectIdsByDataset ??= {};
      this.samplingDefectIdsByDataset[datasetId] = [...new Set(defectIds)];
    },
    clearSamplingDefectIds(datasetId: string): void {
      this.samplingDefectIdsByDataset ??= {};
      delete this.samplingDefectIdsByDataset[datasetId];
    },
  },
});
