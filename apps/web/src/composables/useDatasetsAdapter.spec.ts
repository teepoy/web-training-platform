import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import type { VNode } from 'vue'
import type { Dataset, User } from '../types'

const mockGetImporters = vi.fn()
const mockGetPreviewLaunchers = vi.fn()

vi.mock('../core/registry', () => ({
  pluginRegistry: {
    getImporters: (...args: unknown[]) => mockGetImporters(...args),
    getPreviewLaunchers: (...args: unknown[]) => mockGetPreviewLaunchers(...args),
    getSidebarWidget: vi.fn(),
    getSidebarComponent: vi.fn(),
    getAllSidebarWidgets: vi.fn(() => []),
    registerSidebarWidget: vi.fn(),
    registerImporter: vi.fn(),
    registerExporter: vi.fn(),
    getExporters: vi.fn(() => []),
    registerAgentSkill: vi.fn(),
    getAgentSkills: vi.fn(() => []),
    getAgentSkillByToolName: vi.fn(),
    registerPreviewLauncher: vi.fn(),
  },
}))

import { useDatasetsAdapter } from './useDatasetsAdapter'

function makeDataset(overrides: Partial<Dataset> = {}): Dataset {
  return {
    id: 'ds-1',
    name: 'Test Dataset',
    dataset_type: 'image_classification',
    task_spec: { task_type: 'classification', label_space: ['rose'] },
    created_at: '2026-01-01T00:00:00Z',
    org_id: 'org-1',
    is_public: false,
    ...overrides,
  }
}

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 'user-1',
    email: 'user@test.com',
    name: 'Test User',
    is_superadmin: false,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function buildAdapter(opts: {
  datasets?: Dataset[]
  currentOrgId?: string | null
  user?: User | null
} = {}) {
  const onViewDataset = vi.fn()
  const onTogglePublic = vi.fn()
  const onDeleteDataset = vi.fn()
  const onImportComplete = vi.fn()
  const onPreviewComplete = vi.fn()

  const adapter = useDatasetsAdapter({
    datasets: ref(opts.datasets ?? [makeDataset()]),
    isLoading: ref(false),
    error: ref(null),
    currentOrgId: ref(opts.currentOrgId ?? 'org-1'),
    user: ref(opts.user ?? makeUser()),
    onViewDataset,
    onTogglePublic,
    onDeleteDataset,
    onImportComplete,
    onPreviewComplete,
  })

  return { adapter, onViewDataset, onTogglePublic, onDeleteDataset, onImportComplete, onPreviewComplete }
}

type RenderableColumn = {
  key?: unknown
  render?: (row: Dataset, index: number) => unknown
}

/**
 * Safely extract a handler from the props of a rendered actions-column VNode.
 * The handler key uses Vue 3's camelCase event convention (onXxx).
 */
function extractActionsHandler(
  adapter: ReturnType<typeof useDatasetsAdapter>,
  row: Dataset,
  key: string,
): ((...args: unknown[]) => void) | undefined {
  const col = (adapter.columns.value as RenderableColumn[]).find((c) => c.key === 'actions')
  if (!col?.render) return undefined

  const child = col.render(row, 0)
  const vnode = child !== null && typeof child === 'object' && !Array.isArray(child)
    ? (child as VNode)
    : undefined

  const raw = vnode?.props?.[key]
  return typeof raw === 'function' ? (raw as (...args: unknown[]) => void) : undefined
}

describe('useDatasetsAdapter', () => {
  beforeEach(() => {
    mockGetImporters.mockReset().mockReturnValue([])
    mockGetPreviewLaunchers.mockReset().mockReturnValue([])
  })

  describe('row navigation', () => {
    it('getRowProps.onClick calls onViewDataset with the row id', () => {
      const { adapter, onViewDataset } = buildAdapter()
      const row = makeDataset({ id: 'ds-nav-1' })

      adapter.getRowProps(row).onClick()

      expect(onViewDataset).toHaveBeenCalledOnce()
      expect(onViewDataset).toHaveBeenCalledWith('ds-nav-1')
    })

    it('tableProps.onRowClick calls onViewDataset with the row id', () => {
      const { adapter, onViewDataset } = buildAdapter()
      const row = makeDataset({ id: 'ds-nav-2' })

      adapter.tableProps.value.onRowClick(row)

      expect(onViewDataset).toHaveBeenCalledOnce()
      expect(onViewDataset).toHaveBeenCalledWith('ds-nav-2')
    })
  })

  describe('row action props', () => {
    it('reflects isSuperadmin true for a superadmin user', () => {
      const { adapter } = buildAdapter({ user: makeUser({ is_superadmin: true }) })
      expect(adapter.getRowActionProps(makeDataset()).isSuperadmin).toBe(true)
    })

    it('reflects isSuperadmin false for a regular user', () => {
      const { adapter } = buildAdapter({ user: makeUser({ is_superadmin: false }) })
      expect(adapter.getRowActionProps(makeDataset()).isSuperadmin).toBe(false)
    })

    it('marks isOwnOrg true when dataset org matches the current org', () => {
      const { adapter } = buildAdapter({ currentOrgId: 'org-1' })
      const row = makeDataset({ org_id: 'org-1' })
      expect(adapter.getRowActionProps(row).isOwnOrg).toBe(true)
    })

    it('marks isOwnOrg false when dataset org differs from the current org', () => {
      const { adapter } = buildAdapter({ currentOrgId: 'org-1' })
      const row = makeDataset({ org_id: 'org-other' })
      expect(adapter.getRowActionProps(row).isOwnOrg).toBe(false)
    })
  })

  describe('actions column – delete permission gate', () => {
    it('does not forward delete for a non-superadmin user', () => {
      const { adapter, onDeleteDataset } = buildAdapter({
        user: makeUser({ is_superadmin: false }),
      })
      const row = makeDataset()
      extractActionsHandler(adapter, row, 'onDelete')?.(row)
      expect(onDeleteDataset).not.toHaveBeenCalled()
    })

    it('forwards delete for a superadmin in their own org', () => {
      const { adapter, onDeleteDataset } = buildAdapter({
        user: makeUser({ is_superadmin: true }),
        currentOrgId: 'org-1',
      })
      const row = makeDataset({ org_id: 'org-1' })
      extractActionsHandler(adapter, row, 'onDelete')?.(row)
      expect(onDeleteDataset).toHaveBeenCalledOnce()
      expect(onDeleteDataset).toHaveBeenCalledWith(row)
    })
  })

  describe('actions column – toggle-public permission gate', () => {
    it('does not forward toggle-public for a non-superadmin user', () => {
      const { adapter, onTogglePublic } = buildAdapter({
        user: makeUser({ is_superadmin: false }),
      })
      const row = makeDataset()
      extractActionsHandler(adapter, row, 'onTogglePublic')?.({ id: row.id, isPublic: true })
      expect(onTogglePublic).not.toHaveBeenCalled()
    })

    it('forwards toggle-public for a superadmin in their own org', () => {
      const { adapter, onTogglePublic } = buildAdapter({
        user: makeUser({ is_superadmin: true }),
        currentOrgId: 'org-1',
      })
      const row = makeDataset({ org_id: 'org-1' })
      const payload = { id: row.id, isPublic: true }
      extractActionsHandler(adapter, row, 'onTogglePublic')?.(payload)
      expect(onTogglePublic).toHaveBeenCalledOnce()
      expect(onTogglePublic).toHaveBeenCalledWith(payload)
    })
  })

  describe('toolbar plugin sources', () => {
    it('importerPlugins are sourced from pluginRegistry.getImporters("dataset")', () => {
      const stub = { id: 'stub-importer', label: 'Stub Importer', surfaces: ['dataset'], component: {} }
      mockGetImporters.mockReturnValue([stub])

      const { adapter } = buildAdapter()
      const plugins = adapter.toolbarProps.value.importerPlugins

      expect(mockGetImporters).toHaveBeenCalledWith('dataset')
      expect(plugins).toHaveLength(1)
      expect(plugins[0].id).toBe('stub-importer')
      expect(plugins[0].label).toBe('Stub Importer')
    })

    it('previewLauncherPlugins are sourced from pluginRegistry.getPreviewLaunchers("dataset-list")', () => {
      const stub = { id: 'stub-preview', label: 'Stub Preview', surfaces: ['dataset-list'], component: {} }
      mockGetPreviewLaunchers.mockReturnValue([stub])

      const { adapter } = buildAdapter()
      const plugins = adapter.toolbarProps.value.previewLauncherPlugins

      expect(mockGetPreviewLaunchers).toHaveBeenCalledWith('dataset-list')
      expect(plugins).toHaveLength(1)
      expect(plugins[0].id).toBe('stub-preview')
      expect(plugins[0].label).toBe('Stub Preview')
    })

    it('returns empty arrays when the registry has no matching plugins', () => {
      mockGetImporters.mockReturnValue([])
      mockGetPreviewLaunchers.mockReturnValue([])

      const { adapter } = buildAdapter()

      expect(adapter.toolbarProps.value.importerPlugins).toEqual([])
      expect(adapter.toolbarProps.value.previewLauncherPlugins).toEqual([])
    })
  })

  describe('datasets normalization', () => {
    it('returns an empty array when datasets is null', () => {
      const adapter = useDatasetsAdapter({
        datasets: ref(null),
        isLoading: ref(false),
        error: ref(null),
        currentOrgId: ref(null),
        user: ref(null),
        onViewDataset: vi.fn(),
        onTogglePublic: vi.fn(),
        onDeleteDataset: vi.fn(),
        onImportComplete: vi.fn(),
        onPreviewComplete: vi.fn(),
      })
      expect(adapter.datasets.value).toEqual([])
    })

    it('normalises is_public to false when absent', () => {
      const raw = makeDataset({ is_public: undefined })
      const { adapter } = buildAdapter({ datasets: [raw] })
      expect(adapter.datasets.value[0].is_public).toBe(false)
    })
  })
})
