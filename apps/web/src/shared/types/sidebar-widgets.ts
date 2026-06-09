import type { DatasetAnnotationStats } from "@/generated/orval/models";

export interface ClassifyDashboardContext {
  stats: DatasetAnnotationStats | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  draftCount: number;
  selectedCount: number;
  labelSpace: string[];
  refetch: () => void;
}

export interface SidebarAnnotationGridItem {
  id: string;
  imageSrcs?: string[];
  draftLabel?: string | null;
  predictionLabel?: string | null;
  predictionConfidence?: number | null;
  currentLabel?: string | null;
}

export interface MetricCardItem {
  label: string;
  value: string | number;
  color?: string;
}

export interface MarkdownLogEntry {
  ts: string;
  level: string;
  message: string;
}
