import type { Component, ComputedRef, Ref } from "vue";
import type { DataTableColumns } from "naive-ui";

import type { FlowCard } from "@/shared";

export type MaybeRef<T> = T | Ref<T> | ComputedRef<T>;

export interface DatasetListTaskSpec {
  task_type?: string | null;
}

export interface DatasetListItem {
  id: string;
  name: string;
  dataset_type: string;
  task_spec?: DatasetListTaskSpec | null;
  created_at: string;
  ls_project_id?: string | null;
  ls_project_url?: string | null;
  org_id?: string | null;
  org_name?: string | null;
  is_public?: boolean | null;
}

export interface DatasetListUser {
  is_superadmin?: boolean;
}

export interface DatasetFlow {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  component: Component;
}

export interface DatasetPageShellProps {
  isLoading: boolean;
  hasOrg: boolean;
  error: Error | null;
}

export interface DatasetToolbarProps {
  importerFlows: FlowCard[];
  previewLauncherFlows: FlowCard[];
}

export interface DatasetListPermissions {
  isSuperadmin: boolean;
  hasOrg: boolean;
  canTogglePublic: boolean;
  canDelete: boolean;
}

export interface BuildDatasetColumnsOptions<TDataset extends DatasetListItem = DatasetListItem> {
  currentOrgId: string | null;
  isSuperadmin: boolean;
  taskTagType?: "default" | "error" | "primary" | "info" | "success" | "warning";
  resolveTaskType?: (taskType: string | null | undefined) => string;
  onViewDataset: (datasetId: string) => void;
  onTogglePublic: (payload: { id: string; isPublic: boolean }) => void;
  onDeleteDataset: (dataset: TDataset) => void;
}

export interface UseDatasetListSurfaceOptions<
  TDataset extends DatasetListItem = DatasetListItem,
  TUser extends DatasetListUser = DatasetListUser,
> {
  datasets: MaybeRef<TDataset[] | null | undefined>;
  isLoading: MaybeRef<boolean>;
  error: MaybeRef<Error | null | undefined>;
  currentOrgId: MaybeRef<string | null>;
  user: MaybeRef<TUser | null>;
  importerFlows?: MaybeRef<DatasetFlow[]>;
  previewLauncherFlows?: MaybeRef<DatasetFlow[]>;
  taskTagType?: MaybeRef<"default" | "error" | "primary" | "info" | "success" | "warning">;
  resolveTaskType?: (taskType: string | null | undefined) => string;
  onViewDataset: (datasetId: string) => void;
  onTogglePublic: (payload: { id: string; isPublic: boolean }) => void;
  onDeleteDataset: (dataset: TDataset) => void;
}

export interface UseDatasetListSurfaceResult<TDataset extends DatasetListItem = DatasetListItem> {
  datasets: ComputedRef<TDataset[]>;
  pageShellProps: ComputedRef<DatasetPageShellProps>;
  toolbarProps: ComputedRef<DatasetToolbarProps>;
  permissions: ComputedRef<DatasetListPermissions>;
  tableProps: ComputedRef<{
    datasets: TDataset[];
    columns: DataTableColumns<TDataset>;
    onRowClick: (row: TDataset) => void;
  }>;
  columns: ComputedRef<DataTableColumns<TDataset>>;
  getRowProps: (row: TDataset) => { onClick: () => void };
  getRowActionProps: (row: TDataset) => {
    row: TDataset;
    isSuperadmin: boolean;
    isOwnOrg: boolean;
  };
}
