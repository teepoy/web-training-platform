import { defineStore } from "pinia";
import { listOrganizationsApiV1OrganizationsGet } from "@/generated/orval/endpoints/api";
import type { Organization } from "@/shared/api/types";
import type { MembershipResponse } from "@/generated/orval/models/membershipResponse";

const ORG_KEY = "current_org_id";

function _persistOrg(id: string | null) {
  if (id) {
    localStorage.setItem(ORG_KEY, id);
  } else {
    localStorage.removeItem(ORG_KEY);
  }
}

function _validateAndSelect(currentOrgId: string | null, orgIds: string[]): string | null {
  if (currentOrgId && orgIds.includes(currentOrgId)) {
    return currentOrgId;
  }
  if (orgIds.length === 1) {
    return orgIds[0];
  }
  return null;
}

export const useOrgStore = defineStore("org", {
  state: () => ({
    currentOrgId: null as string | null,
    organizations: [] as Organization[],
    _queryClient: null as { invalidateQueries: () => void } | null,
  }),
  getters: {
    currentOrg: (state) => state.organizations.find((o) => o.id === state.currentOrgId) ?? null,
    hasOrg: (state) => state.currentOrgId !== null,
  },
  actions: {
    async fetchOrganizations() {
      const orgs = await listOrganizationsApiV1OrganizationsGet();
      this.organizations = orgs;

      const orgIds = orgs.map((o) => o.id);
      const selected = _validateAndSelect(this.currentOrgId, orgIds);
      if (selected !== this.currentOrgId) {
        this.currentOrgId = selected;
        _persistOrg(selected);
        this._queryClient?.invalidateQueries();
      }
    },

    setCurrentOrg(orgId: string) {
      this.currentOrgId = orgId;
      _persistOrg(orgId);
      this._queryClient?.invalidateQueries();
    },

    initFromStorage() {
      const stored = localStorage.getItem(ORG_KEY);
      if (stored) {
        this.currentOrgId = stored;
      }
    },

    syncFromMeResponse(memberships: MembershipResponse[]) {
      const orgIds = memberships.map((m) => m.org_id);
      const selected = _validateAndSelect(this.currentOrgId, orgIds);
      if (selected !== this.currentOrgId) {
        this.currentOrgId = selected;
        _persistOrg(selected);
        this._queryClient?.invalidateQueries();
      }
    },
  },
});
