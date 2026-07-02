import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import type { VNode } from "vue";

import { useDatasetListSurface } from "./surface";
import type { DatasetListItem, DatasetListUser, UseDatasetListSurfaceResult } from "./types";

function makeDataset(overrides: Partial<DatasetListItem> = {}): DatasetListItem {
  return {
    id: "ds-1",
    name: "Test Dataset",
    dataset_type: "image_classification",
    task_spec: { task_type: "classification" },
    created_at: "2026-01-01T00:00:00Z",
    org_id: "org-1",
    is_public: false,
    ...overrides,
  };
}

function makeUser(overrides: Partial<DatasetListUser> = {}): DatasetListUser {
  return {
    is_superadmin: false,
    ...overrides,
  };
}

function buildSurface(
  opts: {
    datasets?: DatasetListItem[];
    currentOrgId?: string | null;
    user?: DatasetListUser | null;
    importerFlows?: Array<{ id: string; label: string; component: object }>;
    previewLauncherFlows?: Array<{ id: string; label: string; component: object }>;
  } = {},
) {
  const onViewDataset = vi.fn();
  const onTogglePublic = vi.fn();
  const onDeleteDataset = vi.fn();

  const surface = useDatasetListSurface({
    datasets: ref(opts.datasets ?? [makeDataset()]),
    isLoading: ref(false),
    error: ref(null),
    currentOrgId: ref(opts.currentOrgId ?? "org-1"),
    user: ref(opts.user ?? makeUser()),
    importerFlows: ref(opts.importerFlows ?? []),
    previewLauncherFlows: ref(opts.previewLauncherFlows ?? []),
    onViewDataset,
    onTogglePublic,
    onDeleteDataset,
  });

  return { surface, onViewDataset, onTogglePublic, onDeleteDataset };
}

type RenderableColumn = {
  key?: unknown;
  render?: (row: DatasetListItem, index: number) => unknown;
};

function extractActionsHandler(
  surface: UseDatasetListSurfaceResult<DatasetListItem>,
  row: DatasetListItem,
  key: string,
): ((...args: unknown[]) => void) | undefined {
  const col = (surface.columns.value as RenderableColumn[]).find(
    (candidate) => candidate.key === "actions",
  );
  if (!col?.render) {
    return undefined;
  }

  const child = col.render(row, 0);
  const vnode =
    child !== null && typeof child === "object" && !Array.isArray(child)
      ? (child as VNode)
      : undefined;
  const raw = vnode?.props?.[key];
  return typeof raw === "function" ? (raw as (...args: unknown[]) => void) : undefined;
}

describe("useDatasetListSurface", () => {
  describe("row navigation", () => {
    it("getRowProps.onClick calls onViewDataset with the row id", () => {
      const { surface, onViewDataset } = buildSurface();
      const row = makeDataset({ id: "ds-nav-1" });

      surface.getRowProps(row).onClick();

      expect(onViewDataset).toHaveBeenCalledOnce();
      expect(onViewDataset).toHaveBeenCalledWith("ds-nav-1");
    });

    it("tableProps.onRowClick calls onViewDataset with the row id", () => {
      const { surface, onViewDataset } = buildSurface();
      const row = makeDataset({ id: "ds-nav-2" });

      surface.tableProps.value.onRowClick(row);

      expect(onViewDataset).toHaveBeenCalledOnce();
      expect(onViewDataset).toHaveBeenCalledWith("ds-nav-2");
    });
  });

  describe("row action props", () => {
    it("reflects isSuperadmin true for a superadmin user", () => {
      const { surface } = buildSurface({ user: makeUser({ is_superadmin: true }) });
      expect(surface.getRowActionProps(makeDataset()).isSuperadmin).toBe(true);
    });

    it("marks isOwnOrg false when dataset org differs from the current org", () => {
      const { surface } = buildSurface({ currentOrgId: "org-1" });
      const row = makeDataset({ org_id: "org-other" });
      expect(surface.getRowActionProps(row).isOwnOrg).toBe(false);
    });
  });

  describe("actions column permission gates", () => {
    it("does not forward delete for a non-creator user", () => {
      const { surface, onDeleteDataset } = buildSurface({
        user: makeUser({ id: "other-user", is_superadmin: true }),
      });

      const row = makeDataset({ created_by: "creator-user" });
      extractActionsHandler(surface, row, "onDelete")?.(row);

      expect(onDeleteDataset).not.toHaveBeenCalled();
    });

    it("forwards delete for the creator", () => {
      const { surface, onDeleteDataset } = buildSurface({
        user: makeUser({ id: "creator-user" }),
      });

      const row = makeDataset({ created_by: "creator-user" });
      extractActionsHandler(surface, row, "onDelete")?.(row);

      expect(onDeleteDataset).toHaveBeenCalledOnce();
      expect(onDeleteDataset).toHaveBeenCalledWith(row);
    });

    it("does not forward toggle-public for a non-superadmin user", () => {
      const { surface, onTogglePublic } = buildSurface({
        user: makeUser({ is_superadmin: false }),
      });

      const row = makeDataset();
      extractActionsHandler(surface, row, "onTogglePublic")?.({ id: row.id, isPublic: true });

      expect(onTogglePublic).not.toHaveBeenCalled();
    });

    it("does not forward toggle-public for a superadmin", () => {
      const { surface, onTogglePublic } = buildSurface({ user: makeUser({ is_superadmin: true }) });

      const row = makeDataset();
      const payload = { id: row.id, isPublic: true };
      extractActionsHandler(surface, row, "onTogglePublic")?.(payload);

      expect(onTogglePublic).not.toHaveBeenCalled();
    });
  });

  describe("toolbar plugins", () => {
    it("maps importer and preview launcher descriptors to plugin cards", () => {
      const importer = { id: "stub-importer", label: "Stub Importer", component: {} };
      const preview = { id: "stub-preview", label: "Stub Preview", component: {} };

      const { surface } = buildSurface({
        importerFlows: [importer],
        previewLauncherFlows: [preview],
      });

      expect(surface.toolbarProps.value.importerFlows).toEqual([importer]);
      expect(surface.toolbarProps.value.previewLauncherFlows).toEqual([preview]);
    });
  });

  describe("datasets normalization", () => {
    it("returns an empty array when datasets is null", () => {
      const surface = useDatasetListSurface({
        datasets: ref(null),
        isLoading: ref(false),
        error: ref(null),
        currentOrgId: ref(null),
        user: ref(null),
        onViewDataset: vi.fn(),
        onTogglePublic: vi.fn(),
        onDeleteDataset: vi.fn(),
      });

      expect(surface.datasets.value).toEqual([]);
    });

    it("normalizes is_public to false when absent", () => {
      const raw = makeDataset({ is_public: undefined });
      const { surface } = buildSurface({ datasets: [raw] });

      expect(surface.datasets.value[0].is_public).toBe(false);
    });
  });
});
