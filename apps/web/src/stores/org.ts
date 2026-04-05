import { defineStore } from 'pinia'
import type { Organization } from '../types'
import { fetchOrganizations } from '../api'

const ORG_KEY = 'current_org_id'

export const useOrgStore = defineStore('org', {
  state: () => ({
    currentOrgId: null as string | null,
    organizations: [] as Organization[],
    _queryClient: null as { invalidateQueries: () => void } | null,
  }),
  getters: {
    currentOrg: (state) => state.organizations.find(o => o.id === state.currentOrgId) ?? null,
    hasOrg: (state) => state.currentOrgId !== null,
  },
  actions: {
    async fetchOrganizations() {
      const orgs = await fetchOrganizations()
      this.organizations = orgs
      if (orgs.length === 1 && this.currentOrgId === null) {
        this.currentOrgId = orgs[0].id
        localStorage.setItem(ORG_KEY, orgs[0].id)
      }
    },
    setCurrentOrg(orgId: string) {
      this.currentOrgId = orgId
      localStorage.setItem(ORG_KEY, orgId)
      this._queryClient?.invalidateQueries()
    },
    initFromStorage() {
      const stored = localStorage.getItem(ORG_KEY)
      if (stored) {
        this.currentOrgId = stored
      }
    },
  },
})
