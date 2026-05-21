import { defineStore } from "pinia";

export const useUiStore = defineStore("ui", {
  state: () => ({
    sidebarCollapsed: false,
    darkMode: true,
    toastQueue: [] as Array<{ type: string; message: string }>,
  }),
  actions: {
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed;
    },
    toggleDarkMode() {
      this.darkMode = !this.darkMode;
    },
    showToast(type: string, message: string) {
      this.toastQueue.push({ type, message });
    },
    dismissToast(index: number) {
      this.toastQueue.splice(index, 1);
    },
  },
});
