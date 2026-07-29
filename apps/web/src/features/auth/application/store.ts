import { defineStore } from "pinia";
import {
  loginApiV1AuthLoginPost,
  authMeApiV1AuthMeGet,
  registerApiV1AuthRegisterPost,
} from "@/generated/orval/endpoints/api";
import type {
  UserResponse as User,
  UserWithOrgsResponse as UserWithOrgs,
  LoginResponse,
} from "@/generated/orval/models";
import { useOrgStore } from "./org";

const TOKEN_KEY = "auth_token";
const USER_KEY = "auth_user";

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }

  try {
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(window.atob(padded)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function isTokenExpired(token: string): boolean {
  const payload = decodeJwtPayload(token);
  const exp = payload?.exp;
  return typeof exp === "number" ? Date.now() >= exp * 1000 : false;
}

function parseStoredUser(): User | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as User;
  } catch {
    localStorage.removeItem(USER_KEY);
    return null;
  }
}

export function getStoredToken(): string | null {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    return null;
  }

  if (isTokenExpired(token)) {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem("current_org_id");
    return null;
  }

  return token;
}

export function clearStoredAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem("current_org_id");
}

/**
 * Resolve auth-enabled mode from VITE_AUTH_ENABLED env var.
 *
 * - `VITE_AUTH_ENABLED=true` or `'1'` → enabled
 * - `VITE_AUTH_ENABLED=false` or `'0'` → disabled
 * - Not set → enabled in production (`!import.meta.env.DEV`)
 */
function resolveAuthEnabled(): boolean {
  const val = import.meta.env.VITE_AUTH_ENABLED;
  if (val === "true" || val === "1") return true;
  if (val === "false" || val === "0") return false;
  return !import.meta.env.DEV;
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: parseStoredUser(),
    token: getStoredToken(),
    authEnabled: resolveAuthEnabled(),
  }),
  getters: {
    isAuthenticated: (state) => (state.authEnabled ? state.token !== null : state.user !== null),
  },
  actions: {
    setAuthEnabled(authEnabled: boolean) {
      this.authEnabled = authEnabled;
      if (!authEnabled) {
        this.token = null;
        localStorage.removeItem(TOKEN_KEY);
      }
    },

    async login(email: string, password: string) {
      const loginData: LoginResponse = await loginApiV1AuthLoginPost({ email, password });
      const token = loginData.access_token;
      localStorage.setItem(TOKEN_KEY, token);
      const me = await authMeApiV1AuthMeGet({ headers: { Authorization: `Bearer ${token}` } });
      this.token = token;
      this.user = me;
      localStorage.setItem(USER_KEY, JSON.stringify(me));
      try {
        useOrgStore().syncFromMeResponse(me.organizations ?? []);
      } catch {
        // org store may not be available
      }
    },

    async register(name: string, email: string, password: string) {
      await registerApiV1AuthRegisterPost({ name, email, password });
      await this.login(email, password);
    },

    async oauthLogin(token: string) {
      localStorage.setItem(TOKEN_KEY, token);
      const user = await authMeApiV1AuthMeGet({ headers: { Authorization: `Bearer ${token}` } });
      this.token = token;
      this.user = user;
      localStorage.setItem(USER_KEY, JSON.stringify(user));
      try {
        useOrgStore().syncFromMeResponse(user.organizations ?? []);
      } catch {
        // org store may not be available
      }
    },

    logout() {
      this.user = null;
      this.token = null;
      clearStoredAuth();
      try {
        useOrgStore().$reset();
      } catch {
        // org store may not be available
      }
    },

    hydrateFromStorage() {
      this.token = this.authEnabled ? getStoredToken() : null;
      this.user = parseStoredUser();
    },

    async initFromStorage() {
      this.hydrateFromStorage();
      if (!this.authEnabled) {
        try {
          const user = await authMeApiV1AuthMeGet();
          this.token = null;
          this.user = user;
          localStorage.setItem(USER_KEY, JSON.stringify(user));
          try {
            useOrgStore().syncFromMeResponse(user.organizations ?? []);
          } catch {
            // org store may not be available
          }
        } catch {
          this.user = null;
          localStorage.removeItem(USER_KEY);
        }
        return;
      }

      const token = this.token;
      if (!token) return;
      try {
        const user = await authMeApiV1AuthMeGet({
          headers: { Authorization: `Bearer ${token}` },
        });
        this.token = token;
        this.user = user;
        localStorage.setItem(USER_KEY, JSON.stringify(user));
        try {
          useOrgStore().syncFromMeResponse(user.organizations ?? []);
        } catch {
          // org store may not be available
        }
      } catch {
        this.logout();
      }
    },
  },
});
