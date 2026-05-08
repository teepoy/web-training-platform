import { computed, h, unref } from "vue";
import { NTag, type DataTableColumns } from "naive-ui";

import DatasetRowActions from "../components/datasets/DatasetRowActions.vue";
import type {
  BuildDatasetColumnsOptions,
  DatasetListItem,
  DatasetListUser,
  DatasetPlugin,
  UseDatasetListSurfaceOptions,
  UseDatasetListSurfaceResult,
} from "./types";
import type { PluginCard } from "../plugin-flow";

export function resolveDefaultDatasetTaskType(taskType: string | null | undefined): string {
  return taskType === "vqa" ? "vqa" : "classification";
}

function normalizeDataset<TDataset extends DatasetListItem>(dataset: TDataset): TDataset {
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

function getDatasetOrgLabel(dataset: DatasetListItem, currentOrgId: string | null): string | null {
  if (!dataset.is_public || dataset.org_id === currentOrgId) {
    return null;
  }

  return dataset.org_name?.trim() || "Other Org";
}

export function buildDatasetColumns<TDataset extends DatasetListItem>(
  options: BuildDatasetColumnsOptions<TDataset>,
): DataTableColumns<TDataset> {
  const resolveTaskType = options.resolveTaskType ?? resolveDefaultDatasetTaskType;

  return [
    {
      title: "Name",
      key: "name",
      render: (row: TDataset) => {
        const nodes = [h("span", { style: "font-weight: 500" }, row.name)];
        if (row.is_public) {
          nodes.push(
            h(NTag, { type: "info", size: "small", style: "margin-left: 6px" }, { default: () => "Public" }),
          );
        }

        const orgLabel = getDatasetOrgLabel(row, options.currentOrgId);
        if (orgLabel) {
          nodes.push(h("span", { style: "margin-left: 4px; font-size: 12px; color: #aaa" }, `(${orgLabel})`));
        }

        return h("span", {}, nodes);
      },
    },
    {
      title: "Dataset Type",
      key: "dataset_type",
      render: (row: TDataset) => h(NTag, { type: "default", size: "small" }, { default: () => row.dataset_type }),
    },
    {
      title: "Task Type",
      key: "task_type",
      render: (row: TDataset) =>
        h(
          NTag,
          { type: options.taskTagType ?? "info", size: "small" },
          { default: () => resolveTaskType(row.task_spec?.task_type) },
        ),
    },
    {
      title: "Created At",
      key: "created_at",
      render: (row: TDataset) => h("span", {}, new Date(row.created_at).toLocaleString()),
    },
    {
      title: "Actions",
      key: "actions",
      render: (row: TDataset) =>
        h(DatasetRowActions, {
          row,
          isSuperadmin: options.isSuperadmin,
          isOwnOrg: row.org_id === options.currentOrgId,
          onView: (id: string) => {
            options.onViewDataset(id);
          },
          onTogglePublic: (payload: { id: string; isPublic: boolean }) => {
            if (!options.isSuperadmin) {
              return;
            }

            options.onTogglePublic(payload);
          },
          onDelete: (dataset: DatasetListItem) => {
            if (!options.isSuperadmin) {
              return;
            }

            options.onDeleteDataset(dataset as TDataset);
          },
        }),
    },
  ];
}

export function useDatasetListSurface<
  TDataset extends DatasetListItem,
  TUser extends DatasetListUser = DatasetListUser,
>(options: UseDatasetListSurfaceOptions<TDataset, TUser>): UseDatasetListSurfaceResult<TDataset> {
  const resolvedDatasets = computed<TDataset[]>(() => {
    const input = unref(options.datasets) ?? [];
    return input.map((dataset) => normalizeDataset(dataset));
  });

  const resolvedCurrentOrgId = computed(() => unref(options.currentOrgId));
  const resolvedUser = computed(() => unref(options.user));

  const permissions = computed(() => {
    const isSuperadmin = resolvedUser.value?.is_superadmin === true;
    const hasOrg = resolvedCurrentOrgId.value !== null;

    return {
      isSuperadmin,
      hasOrg,
      canTogglePublic: isSuperadmin && hasOrg,
      canDelete: isSuperadmin && hasOrg,
    };
  });

  const pageShellProps = computed(() => ({
    isLoading: unref(options.isLoading),
    hasOrg: permissions.value.hasOrg,
    error: unref(options.error) ?? null,
  }));

  const toolbarProps = computed(() => ({
    importerPlugins: (unref(options.importerPlugins) ?? []).map((plugin) => toPluginCard(plugin)),
    previewLauncherPlugins: (unref(options.previewLauncherPlugins) ?? []).map((plugin) => toPluginCard(plugin)),
  }));

  function getRowProps(row: TDataset): { onClick: () => void } {
    return {
      onClick: () => {
        options.onViewDataset(row.id);
      },
    };
  }

  function getRowActionProps(row: TDataset) {
    return {
      row,
      isSuperadmin: permissions.value.isSuperadmin,
      isOwnOrg: row.org_id === resolvedCurrentOrgId.value,
    };
  }

  const columns = computed<DataTableColumns<TDataset>>(() =>
    buildDatasetColumns<TDataset>({
      currentOrgId: resolvedCurrentOrgId.value,
      isSuperadmin: permissions.value.isSuperadmin,
      taskTagType: unref(options.taskTagType) ?? "info",
      resolveTaskType: options.resolveTaskType,
      onViewDataset: options.onViewDataset,
      onTogglePublic: (payload) => {
        if (!permissions.value.canTogglePublic) {
          return;
        }

        options.onTogglePublic(payload);
      },
      onDeleteDataset: (dataset) => {
        if (!permissions.value.canDelete) {
          return;
        }

        options.onDeleteDataset(dataset);
      },
    }),
  );

  const tableProps = computed(() => ({
    datasets: resolvedDatasets.value,
    columns: columns.value,
    onRowClick: (row: TDataset) => {
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
