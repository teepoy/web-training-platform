import { computed, h, unref, type Component, type ComputedRef, type Ref } from "vue";
import { NTag, type DataTableColumns } from "naive-ui";

import DatasetRowActions from "../components/datasets/DatasetRowActions.vue";
import { pluginRegistry } from "../core/registry";
import type { Dataset, User } from "../types";
import { resolveDatasetTaskType } from "../views/datasets/registry";

type MaybeRef<T> = T | Ref<T>;

interface PluginCard {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  component: Component;
}

type DatasetPlugin = {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  component: PluginCard["component"];
};

export interface DatasetPageShellProps {
  isLoading: boolean;
  hasOrg: boolean;
  error: Error | null;
}

export interface DatasetToolbarProps {
  importerPlugins: PluginCard[];
  previewLauncherPlugins: PluginCard[];
}

export interface DatasetPermissions {
  isSuperadmin: boolean;
  hasOrg: boolean;
  canTogglePublic: boolean;
  canDelete: boolean;
}

export interface UseDatasetsAdapterOptions {
  datasets: MaybeRef<Dataset[] | null | undefined>;
  isLoading: MaybeRef<boolean>;
  error: MaybeRef<Error | null | undefined>;
  currentOrgId: MaybeRef<string | null>;
  user: MaybeRef<User | null>;
  onViewDataset: (datasetId: string) => void;
  onTogglePublic: (payload: { id: string; isPublic: boolean }) => void;
  onDeleteDataset: (dataset: Dataset) => void;
  onImportComplete: () => void;
  onPreviewComplete: (result: unknown) => void;
}

export interface UseDatasetsAdapterResult {
  datasets: ComputedRef<Dataset[]>;
  pageShellProps: ComputedRef<DatasetPageShellProps>;
  toolbarProps: ComputedRef<DatasetToolbarProps>;
  permissions: ComputedRef<DatasetPermissions>;
  tableProps: ComputedRef<{
    datasets: Dataset[];
    columns: DataTableColumns<Dataset>;
    onRowClick: (row: Dataset) => void;
  }>;
  columns: ComputedRef<DataTableColumns<Dataset>>;
  getRowProps: (row: Dataset) => { onClick: () => void };
  getRowActionProps: (row: Dataset) => {
    row: Dataset;
    isSuperadmin: boolean;
    isOwnOrg: boolean;
  };
}

function normalizeDataset(dataset: Dataset): Dataset {
  return {
    ...dataset,
    ls_project_id: dataset.ls_project_id ?? undefined,
    ls_project_url: dataset.ls_project_url ?? undefined,
    org_id: dataset.org_id ?? undefined,
    org_name: dataset.org_name?.trim() || undefined,
    is_public: dataset.is_public ?? false,
  };
}

function toPluginCard(plugin: DatasetPlugin): PluginCard {
  return {
    id: plugin.id,
    label: plugin.label,
    description: plugin.description,
    icon: plugin.icon,
    component: plugin.component,
  };
}

function getDatasetOrgLabel(dataset: Dataset, currentOrgId: string | null): string | null {
  if (!dataset.is_public || dataset.org_id === currentOrgId) {
    return null;
  }

  return dataset.org_name?.trim() || "Other Org";
}

export function useDatasetsAdapter(options: UseDatasetsAdapterOptions): UseDatasetsAdapterResult {
  const resolvedDatasets = computed<Dataset[]>(() => {
    const input = unref(options.datasets) ?? [];
    return input.map((dataset) => normalizeDataset(dataset));
  });

  const resolvedCurrentOrgId = computed(() => unref(options.currentOrgId));
  const resolvedUser = computed(() => unref(options.user));

  const permissions = computed<DatasetPermissions>(() => {
    const isSuperadmin = resolvedUser.value?.is_superadmin === true;
    const hasOrg = resolvedCurrentOrgId.value !== null;

    return {
      isSuperadmin,
      hasOrg,
      canTogglePublic: isSuperadmin && hasOrg,
      canDelete: isSuperadmin && hasOrg,
    };
  });

  const pageShellProps = computed<DatasetPageShellProps>(() => ({
    isLoading: unref(options.isLoading),
    hasOrg: permissions.value.hasOrg,
    error: unref(options.error) ?? null,
  }));

  const importerPlugins = computed<PluginCard[]>(() =>
    pluginRegistry.getImporters("dataset").map((plugin) => toPluginCard(plugin))
  );

  const previewLauncherPlugins = computed<PluginCard[]>(() =>
    pluginRegistry.getPreviewLaunchers("dataset-list").map((plugin) => toPluginCard(plugin))
  );

  const toolbarProps = computed<DatasetToolbarProps>(() => ({
    importerPlugins: importerPlugins.value,
    previewLauncherPlugins: previewLauncherPlugins.value,
  }));

  function getRowProps(row: Dataset) {
    return {
      onClick: () => {
        options.onViewDataset(row.id);
      },
    };
  }

  function getRowActionProps(row: Dataset) {
    return {
      row,
      isSuperadmin: permissions.value.isSuperadmin,
      isOwnOrg: row.org_id === resolvedCurrentOrgId.value,
    };
  }

  const columns = computed<DataTableColumns<Dataset>>(() => [
    {
      title: "Name",
      key: "name",
      render: (row: Dataset) => {
        const nodes = [h("span", { style: "font-weight: 500" }, row.name)];
        if (row.is_public) {
          nodes.push(
            h(NTag, { type: "info", size: "small", style: "margin-left: 6px" }, { default: () => "Public" })
          );
        }

        const orgLabel = getDatasetOrgLabel(row, resolvedCurrentOrgId.value);
        if (orgLabel) {
          nodes.push(h("span", { style: "margin-left: 4px; font-size: 12px; color: #aaa" }, `(${orgLabel})`));
        }

        return h("span", {}, nodes);
      },
    },
    {
      title: "Dataset Type",
      key: "dataset_type",
      render: (row: Dataset) => h(NTag, { type: "default", size: "small" }, { default: () => row.dataset_type }),
    },
    {
      title: "Task Type",
      key: "task_type",
      render: (row: Dataset) =>
        h(NTag, { type: "info", size: "small" }, { default: () => resolveDatasetTaskType(row.task_spec?.task_type) }),
    },
    {
      title: "Created At",
      key: "created_at",
      render: (row: Dataset) => h("span", {}, new Date(row.created_at).toLocaleString()),
    },
    {
      title: "Actions",
      key: "actions",
      render: (row: Dataset) =>
        h(DatasetRowActions, {
          ...getRowActionProps(row),
          onView: (id: string) => {
            options.onViewDataset(id);
          },
          onTogglePublic: (payload: { id: string; isPublic: boolean }) => {
            if (!permissions.value.canTogglePublic) {
              return;
            }

            options.onTogglePublic(payload);
          },
          onDelete: (dataset: Dataset) => {
            if (!permissions.value.canDelete) {
              return;
            }

            options.onDeleteDataset(dataset);
          },
        }),
    },
  ]);

  const tableProps = computed(() => ({
    datasets: resolvedDatasets.value,
    columns: columns.value,
    onRowClick: (row: Dataset) => {
      options.onViewDataset(row.id);
    },
  }));

  return {
    datasets: resolvedDatasets,
    pageShellProps,
    toolbarProps,
    permissions,
    tableProps,
    columns,
    getRowProps,
    getRowActionProps,
  };
}
