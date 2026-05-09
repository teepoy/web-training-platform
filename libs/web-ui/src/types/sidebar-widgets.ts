export interface ClassifyDashboardStats {
  total_samples: number;
  annotated_samples: number;
  unlabeled_samples: number;
  label_counts?: Record<string, number>;
}

export interface ClassifyDashboardContext {
  stats: ClassifyDashboardStats | null;
  isLoading: boolean;
  isError: boolean;
  draftCount: number;
  selectedCount: number;
  refetch: () => void;
}

export interface AnnotationGridItem {
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
