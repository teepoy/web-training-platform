import { defineStore } from "pinia";

const DARK_MODE_KEY = "ui_dark_mode";

function hydrateDarkMode(): boolean {
  const raw = localStorage.getItem(DARK_MODE_KEY);
  if (raw === null) {
    return false;
  }
  try {
    return JSON.parse(raw) as boolean;
  } catch {
    return false;
  }
}

export const useUiStore = defineStore("ui", {
  state: () => ({
    sidebarCollapsed: false,
    darkMode: hydrateDarkMode(),
    toastQueue: [] as Array<{ type: string; message: string }>,
  }),
  actions: {
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed;
    },
    toggleDarkMode() {
      this.darkMode = !this.darkMode;
      localStorage.setItem(DARK_MODE_KEY, String(this.darkMode));
    },
    showToast(type: string, message: string) {
      this.toastQueue.push({ type, message });
    },
    hydrateDarkMode() {
      this.darkMode = hydrateDarkMode();
    },
    dismissToast(index: number) {
      this.toastQueue.splice(index, 1);
    },
  },
});
