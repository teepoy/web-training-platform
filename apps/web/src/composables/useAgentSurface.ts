/**
 * useAgentSurface — manages the agent-controlled display surface state.
 *
 * Holds the current panels array (from the SurfaceStore backend) and
 * provides methods to refresh, import, and export surface state.
 * Also accepts live panel updates pushed from the agent chat stream.
 */

import { ref, type Ref } from 'vue'
import type { AgentPanelDescriptor, SurfaceStateDocument } from '../types'
import { getSurfaceState, exportSurfaceState, importSurfaceState } from '../api'

export interface UseAgentSurfaceReturn {
  /** Current agent-controlled panels. */
  agentPanels: Ref<AgentPanelDescriptor[]>
  /** Whether we're currently loading surface state. */
  isLoading: Ref<boolean>
  /** Last error message. */
  error: Ref<string | null>
  /** Fetch current state from backend. */
  refresh: () => Promise<void>
  /** Apply a panels array from a sidebar-update SSE event. */
  applyPanelsUpdate: (panels: AgentPanelDescriptor[]) => void
  /** Export surface state. */
  exportState: () => Promise<SurfaceStateDocument | null>
  /** Import surface state. */
  importState: (doc: SurfaceStateDocument) => Promise<void>
  /** Clear all agent panels locally. */
  clear: () => void
}

export function useAgentSurface(
  sessionId: string,
  surfaceId: string,
): UseAgentSurfaceReturn {
  const agentPanels = ref<AgentPanelDescriptor[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function refresh() {
    isLoading.value = true
    error.value = null
    try {
      const state = await getSurfaceState(sessionId, surfaceId)
      agentPanels.value = state.panels
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      isLoading.value = false
    }
  }

  function applyPanelsUpdate(panels: AgentPanelDescriptor[]) {
    agentPanels.value = panels
  }

  async function doExport(): Promise<SurfaceStateDocument | null> {
    try {
      return await exportSurfaceState(sessionId, surfaceId)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      return null
    }
  }

  async function doImport(doc: SurfaceStateDocument) {
    isLoading.value = true
    error.value = null
    try {
      const state = await importSurfaceState(sessionId, surfaceId, doc)
      agentPanels.value = state.panels
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      isLoading.value = false
    }
  }

  function clear() {
    agentPanels.value = []
  }

  return {
    agentPanels,
    isLoading,
    error,
    refresh,
    applyPanelsUpdate,
    exportState: doExport,
    importState: doImport,
    clear,
  }
}
