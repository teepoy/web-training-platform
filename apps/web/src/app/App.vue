<template>
  <n-config-provider :theme="computedTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-notification-provider>
        <n-dialog-provider>
          <template v-if="isAuthPage">
            <RouterView />
          </template>
          <template v-else-if="isSettingsRoute || isAdminRoute">
            <RouterView />
            <AgentChatDrawer
              :messages="globalAgent.messages.value"
              :status="globalAgent.status.value"
              @send="globalAgent.send"
              @abort="globalAgent.abort"
              @clear="globalAgent.clearHistory"
            />
          </template>
          <template v-else>
            <n-layout has-sider style="height: 100vh">
              <n-layout-sider
                :collapsed="effectiveSidebarCollapsed"
                :width="240"
                :collapsed-width="isNarrowScreen ? 56 : 64"
                collapse-mode="width"
                bordered
                :show-trigger="!isNarrowScreen"
                @collapse="uiStore.sidebarCollapsed = true"
                @expand="uiStore.sidebarCollapsed = false"
              >
                <n-menu
                  :collapsed="effectiveSidebarCollapsed"
                  :options="menuOptions"
                  :value="activeRoute"
                  @update:value="(key: string) => router.push(key)"
                />
              </n-layout-sider>
              <n-layout vertical>
                <n-layout-header
                  v-if="showAppHeader"
                  bordered
                  style="
                    height: 48px;
                    display: flex;
                    align-items: center;
                    padding: 0 16px;
                    gap: 12px;
                  "
                >
                  <span style="font-weight: 600; flex: 1">ML Training Platform</span>
                  <n-button text @click="uiStore.toggleDarkMode">{{
                    uiStore.darkMode ? "☀" : "🌙"
                  }}</n-button>
                  <n-dropdown
                    trigger="click"
                    :options="avatarDropdownOptions"
                    @select="handleAvatarSelect"
                  >
                    <n-avatar round size="small" style="cursor: pointer" data-testid="nav-avatar">{{
                      userInitials
                    }}</n-avatar>
                  </n-dropdown>
                </n-layout-header>
                <n-layout-content :style="contentStyle">
                  <div style="flex: 1; min-height: 0">
                    <RouterView />
                  </div>
                  <n-back-top />
                </n-layout-content>
              </n-layout>
            </n-layout>
            <AgentChatDrawer
              :messages="globalAgent.messages.value"
              :status="globalAgent.status.value"
              @send="globalAgent.send"
              @abort="globalAgent.abort"
              @clear="globalAgent.clearHistory"
            />
          </template>
        </n-dialog-provider>
      </n-notification-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, h, onMounted, watch, type Component } from "vue";
import { useRouter, useRoute, RouterView } from "vue-router";
import { darkTheme, NIcon, type GlobalThemeOverrides, type MenuOption } from "naive-ui";
import { AlbumsOutline, CubeOutline, ImagesOutline, PulseOutline } from "@vicons/ionicons5";
import { useQueryClient } from "@tanstack/vue-query";
import { useMediaQuery } from "@vueuse/core";
import VxeUI from "vxe-pc-ui";
import { useUiStore } from "@/features/auth/application/ui";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { useAgentAdapter } from "@/features/agent/application/useAgentAdapter";
import { AgentChatDrawer } from "@/shared";

const router = useRouter();
const route = useRoute();
const uiStore = useUiStore();
const authStore = useAuthStore();
const orgStore = useOrgStore();
const queryClient = useQueryClient();
const globalAgent = useAgentAdapter();
const isNarrowScreen = useMediaQuery("(max-width: 767px)");
const effectiveSidebarCollapsed = computed(() => isNarrowScreen.value || uiStore.sidebarCollapsed);

const AUTH_PATHS = ["/login", "/register"];
const isAuthPage = computed(() => AUTH_PATHS.includes(route.path));
const isSettingsRoute = computed(() => route.path.startsWith("/settings"));
const isAdminRoute = computed(() => route.path.startsWith("/admin"));
const showAppHeader = computed(() => route.meta.hideAppHeader !== true);
const contentStyle = computed(() => ({
  padding:
    typeof route.meta.contentPadding === "string"
      ? route.meta.contentPadding
      : isNarrowScreen.value
        ? "16px"
        : "24px",
  overflowY: "auto",
  display: "flex",
  flexDirection: "column",
}));

const computedTheme = computed(() => {
  return uiStore.darkMode ? darkTheme : null;
});

watch(
  () => uiStore.darkMode,
  (darkMode) => VxeUI.setTheme(darkMode ? "dark" : "light"),
  { immediate: true },
);

const themeOverrides: GlobalThemeOverrides = {
  common: {
    fontSizeMedium: "13px",
    fontSizeSmall: "12px",
    borderRadius: "8px",
  },
};

const activeRoute = computed(() => {
  const p = route.path;
  if (
    p.startsWith("/library") ||
    p.startsWith("/datasets") ||
    p.startsWith("/dataset-collections")
  ) {
    return "/library";
  }
  if (p.startsWith("/models")) return "/models";
  if (p.startsWith("/sc")) return "/sc";
  if (p.startsWith("/automations")) return "/automations";
  return p;
});

// Check if current user is an admin (superadmin)
const isAdmin = computed(() => authStore.user?.is_superadmin ?? false);

function renderMenuIcon(icon: Component) {
  return () => h(NIcon, null, { default: () => h(icon) });
}

const menuOptions: MenuOption[] = [
  { label: "Patch", key: "/sc", icon: renderMenuIcon(ImagesOutline) },
  { label: "Library", key: "/library", icon: renderMenuIcon(AlbumsOutline) },
  { label: "Models", key: "/models", icon: renderMenuIcon(CubeOutline) },
  { label: "Automations", key: "/automations", icon: renderMenuIcon(PulseOutline) },
];

const userInitials = computed(() => authStore.user?.name?.slice(0, 2).toUpperCase() ?? "LU");

const avatarDropdownOptions = computed(() => {
  const options: Array<
    { label: string; key: string; disabled: boolean } | { type: "divider"; key: string }
  > = [
    { label: authStore.user?.name || "Local User", key: "name", disabled: true },
    { type: "divider" as const, key: "d1" },
    { label: "Profile", key: "profile", disabled: true },
    { label: "Settings", key: "settings", disabled: false },
  ];
  if (isAdmin.value) {
    options.push({ label: "Admin", key: "admin", disabled: false });
  }
  if (authStore.authEnabled) {
    options.push({ label: "Logout", key: "logout", disabled: false });
  }
  return options;
});

function handleAvatarSelect(key: string) {
  if (key === "settings") {
    router.push("/settings/access-keys");
    return;
  }
  if (key === "admin") {
    router.push("/admin/dashboard");
    return;
  }
  if (key === "logout") {
    authStore.logout();
    router.push("/login");
  }
}

onMounted(async () => {
  await authStore.initFromStorage();
  orgStore.initFromStorage();
  uiStore.hydrateDarkMode();
  orgStore._queryClient = queryClient;
  if (authStore.isAuthenticated) {
    try {
      await orgStore.fetchOrganizations();
    } catch {
      // org fetch will happen after login
    }
  }
});

watch(
  () => route.fullPath,
  () => {
    if (route.meta.autoCollapseSidebar === true) {
      uiStore.sidebarCollapsed = true;
    }
  },
  { immediate: true },
);
</script>
