import { defineStore } from "pinia";
import type { User } from "../types";
import { authLogin, authRegister, authMe } from "../api";

const TOKEN_KEY = "auth_token";
const USER_KEY = "auth_user";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: null as User | null,
    token: null as string | null,
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
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    },

    async initFromStorage() {
      const token = localStorage.getItem(TOKEN_KEY);
      if (!token) return;
      try {
        const userWithOrgs = await authMe(token);
        this.token = token;
        this.user = userWithOrgs;
      } catch {
        this.user = null;
        this.token = null;
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
      }
    },
  },
});
