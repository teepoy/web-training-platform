import { defineStore } from "pinia";
import { cloneScGlobalFilter, type ScGlobalFilter } from "@/features/sc/domain/globalFilter";

export const useScReclassifyStore = defineStore("scReclassify", {
  state: () => ({
    selectedDefectIdsByDataset: {} as Record<string, string[]>,
    samplingDefectIdsByDataset: {} as Record<string, string[]>,
    globalFiltersByWorkspace: {} as Record<string, ScGlobalFilter>,
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
    setGlobalFilter(workspaceKey: string, filter: ScGlobalFilter): void {
      this.globalFiltersByWorkspace ??= {};
      this.globalFiltersByWorkspace[workspaceKey] = cloneScGlobalFilter(filter);
    },
    clearGlobalFilter(workspaceKey: string): void {
      this.globalFiltersByWorkspace ??= {};
      delete this.globalFiltersByWorkspace[workspaceKey];
    },
  },
});
