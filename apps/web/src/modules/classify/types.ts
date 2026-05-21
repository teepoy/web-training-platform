import type { DatasetAnnotationStats, WaferPoint } from "@/modules/datasets/types";

export interface AnnotationGridItem {
  id: string;
  imageSrcs: string[];
  currentLabel: string | null;
  draftLabel: string | null;
  predictionLabel: string | null;
  predictionConfidence: number | null;
  predictionId: string | null;
  metadata: Record<string, unknown>;
}

export interface BrowserItem {
  id: string;
  imageSrcs: string[];
  metadata: Record<string, unknown>;
  sourceKind?: "dataset" | "preview" | "classify-review";
  currentLabel: string | null;
  draftLabel: string | null;
  predictionLabel: string | null;
  predictionConfidence: number | null;
  predictionId: string | null;
  activationLabel: string | null;
}

export interface SidebarPanelDescriptor {
  id: string;
  component: string;
  title: string;
  props: Record<string, unknown>;
  collapsed?: boolean;
  order?: number;
  size?: "compact" | "normal" | "large";
  _agentOwned?: boolean;
}

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

export interface BlinkSampleInput {
  id: string;
  imageSrcs: string[];
  metadata: Record<string, unknown>;
  label?: string;
}

export interface BlinkColumnDef {
  key: string;
  title: string;
  kind?: "text" | "image";
  width?: number;
}

export type BlinkPhase = "a" | "b";

export interface BlinkRow {
  id: string;
  imageA: string;
  imageB: string;
  metadata: Record<string, unknown>;
  cells: Record<string, string>;
}

export interface BlinkTableDataResult {
  rows: BlinkRow[];
  columns: BlinkColumnDef[];
}

export interface BuildBlinkTableDataOptions {
  maxImageColumns?: number;
  extraColumns?: BlinkColumnDef[];
}

export interface Annotation<TId = string> {
  kind: string;
  ids: Set<TId>;
}

export interface DataNode<TId = string> {
  id: string;
  parentId: string | null;
  annotation: import("vue").ShallowRef<Annotation<TId> | null>;
  child: import("vue").ComputedRef<DataNode<TId> | null>;
  visibleAnnotations: import("vue").ComputedRef<Annotation<TId>[]>;
  annotate: (kind: string, ids: TId[]) => void;
  clear: () => void;
}

export interface DataPipeline<
  TItem extends { id: string },
  TId = string,
> {
  rawItems: import("vue").Ref<TItem[]>;
  register: (id: string, parentId?: string) => DataNode<TId>;
  getNode: (id: string) => DataNode<TId> | undefined;
  nodes: import("vue").ShallowRef<Record<string, DataNode<TId>>>;
}

export type { DatasetAnnotationStats as ClassifyDashboardStats, WaferPoint };
