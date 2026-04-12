import { defineStore } from "pinia";
import type { User } from "../types";
import { authLogin, authRegister, authMe } from "../api";

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
    return null;
  }

  return token;
}

export function clearStoredAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: parseStoredUser(),
    token: getStoredToken(),
  }),
  getters: {
    isAuthenticated: (state) => state.token !== null,
  },
  actions: {
    async login(email: string, password: string) {
      const resp = await authLogin(email, password);
      const token = resp.access_token;
      localStorage.setItem(TOKEN_KEY, token);
      const userWithOrgs = await authMe(token);
      this.token = token;
      this.user = userWithOrgs;
      localStorage.setItem(USER_KEY, JSON.stringify(userWithOrgs));
    },

    async register(name: string, email: string, password: string) {
      await authRegister(name, email, password);
      await this.login(email, password);
    },

    logout() {
      this.user = null;
      this.token = null;
      clearStoredAuth();
    },

    hydrateFromStorage() {
      this.token = getStoredToken();
      this.user = this.token ? parseStoredUser() : null;
    },

    async initFromStorage() {
      this.hydrateFromStorage();
      const token = this.token;
      if (!token) return;
      try {
        const userWithOrgs = await authMe(token);
        this.token = token;
        this.user = userWithOrgs;
        localStorage.setItem(USER_KEY, JSON.stringify(userWithOrgs));
      } catch {
        this.logout();
      }
    },
  },
});
