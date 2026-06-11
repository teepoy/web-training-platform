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
            <!-- Global Agent Chat Drawer (available on settings/admin pages too) -->
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
                :collapsed="uiStore.sidebarCollapsed"
                :width="240"
                :collapsed-width="64"
                collapse-mode="width"
                bordered
                show-trigger
                @collapse="uiStore.sidebarCollapsed = true"
                @expand="uiStore.sidebarCollapsed = false"
              >
                <n-menu
                  :collapsed="uiStore.sidebarCollapsed"
                  :options="menuOptions"
                  :value="activeRoute"
                  @update:value="(key: string) => router.push(key)"
                />
              </n-layout-sider>
              <n-layout vertical>
                <n-layout-header bordered style="height: 48px; display: flex; align-items: center; padding: 0 16px; gap: 12px">
                  <span style="font-weight: 600; flex: 1">ML Training Platform</span>
                  <n-button text @click="uiStore.toggleDarkMode">{{ uiStore.darkMode ? '☀' : '🌙' }}</n-button>
                  <!-- External service links -->
                  <n-button tag="a" :href="labelStudioUrl" target="_blank" text type="primary" size="small">
                    Label Studio ↗
                  </n-button>
                  <template v-if="isAdmin">
                    <n-button tag="a" :href="prefectUrl" target="_blank" text type="primary" size="small">
                      Prefect ↗
                    </n-button>
                    <n-button tag="a" :href="minioUrl" target="_blank" text type="primary" size="small">
                      MinIO ↗
                    </n-button>
                    <n-button tag="a" :href="pgAdminUrl" target="_blank" text type="primary" size="small">
                      pgAdmin ↗
                    </n-button>
                  </template>
                  <n-dropdown
                    trigger="click"
                    :options="avatarDropdownOptions"
                    @select="handleAvatarSelect"
                  >
                    <n-avatar
                      round
                      size="small"
                      style="cursor: pointer"
                      data-testid="nav-avatar"
                    >{{ userInitials }}</n-avatar>
                  </n-dropdown>
                </n-layout-header>
                <n-layout-content style="padding: 24px; overflow-y: auto; display: flex; flex-direction: column;">
                  <div style="flex: 1; min-height: 0;">
                    <RouterView />
                  </div>
                  <n-back-top />
                </n-layout-content>
              </n-layout>
            </n-layout>
            <!-- Global Agent Chat Drawer (available on all authenticated pages) -->
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
import { computed, onMounted, watch } from "vue";
import { useRouter, useRoute, RouterView } from "vue-router";
import { darkTheme, type GlobalThemeOverrides } from "naive-ui";
import { useQueryClient } from "@tanstack/vue-query";
import { useUiStore } from '@/features/auth/application/ui';
import { useAuthStore } from '@/features/auth/application/store';
import { useOrgStore } from '@/features/auth/application/org';
import { useTaskHandoff, syncWatchedTaskIds } from "@/shared/composables/useTaskHandoff";
import { useTaskHandoffState } from "@/shared/composables/taskHandoffState";
import { useAgentAdapter } from "@/features/agent/application/useAgentAdapter";
import { AgentChatDrawer } from "@/shared";

const router = useRouter();
const route = useRoute();
const uiStore = useUiStore();
const authStore = useAuthStore();
const orgStore = useOrgStore();
const queryClient = useQueryClient();
const { watchedTaskIds } = useTaskHandoffState();
const { watchTask, syncTask } = useTaskHandoff();
const globalAgent = useAgentAdapter();

const AUTH_PATHS = ["/login", "/register"];
const isAuthPage = computed(() => AUTH_PATHS.includes(route.path));
const isSettingsRoute = computed(() => route.path.startsWith("/settings"));
const isAdminRoute = computed(() => route.path.startsWith("/admin"));

const computedTheme = computed(() => {
  return uiStore.darkMode ? darkTheme : null;
});

const themeOverrides: GlobalThemeOverrides = {
  common: {
    fontSizeMedium: "13px",
    fontSizeSmall: "12px",
    borderRadius: "8px",
  },
};

const activeRoute = computed(() => {
  const p = route.path;
  if (p.startsWith("/datasets")) return "/datasets";
  if (p.startsWith("/sc")) return "/sc";
  if (p.startsWith("/sensors")) return "/sensors";
  if (p.startsWith("/preview")) return "/preview";
  if (p.startsWith("/tasks")) return "/tasks";
  return p;
});

// Check if current user is an admin (superadmin)
const isAdmin = computed(() => authStore.user?.is_superadmin ?? false);

// External service URLs - these can be configured via environment variables in production
const labelStudioUrl = "http://localhost:8080";
const prefectUrl = "http://localhost:4200";
const minioUrl = "http://localhost:9001";
const pgAdminUrl = "http://localhost:5050";

const menuOptions = [
  { label: "Preview", key: "/preview" },
  { label: "Task Explorer", key: "/tasks" },
  { label: "Datasets", key: "/datasets" },
  { label: "Semiconductor", key: "/sc" },
  { label: "Automations", key: "/sensors" },
];

const userInitials = computed(() =>
  authStore.user?.name?.slice(0, 2).toUpperCase() ?? "LU",
);

const avatarDropdownOptions = computed(() => {
  const options: Array<{ label: string; key: string; disabled: boolean } | { type: "divider"; key: string }> = [
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

watch(watchedTaskIds, (ids) => {
  void syncWatchedTaskIds(ids, (detail) => {
    const task = {
      id: detail.id,
      task_kind: detail.task_kind,
      execution_kind: detail.derived.execution_kind,
      display_name: String(detail.meta?.trainer_id || detail.meta?.model_id || detail.id),
      display_status: detail.derived.display_status,
      stage: detail.derived.stage,
      dataset_id: String(detail.meta?.dataset_id || ""),
      model_id: detail.meta?.model_id ? String(detail.meta.model_id) : null,
      trainer_id: detail.meta?.trainer_id ? String(detail.meta.trainer_id) : null,
      created_by: String((detail.raw.platform_job?.created_by as string | undefined) || ""),
      created_at: String((detail.raw.platform_job?.created_at as string | undefined) || ""),
      updated_at: String((detail.raw.platform_job?.updated_at as string | undefined) || ""),
      prefect_state: detail.derived.prefect_state ?? null,
      work_pool_name: detail.raw.flow_run?.work_pool_name ? String(detail.raw.flow_run.work_pool_name) : null,
      work_queue_name: detail.raw.flow_run?.work_queue_name ? String(detail.raw.flow_run.work_queue_name) : null,
      queue_priority: detail.derived.queue_priority ?? null,
      queue_priority_label: detail.derived.queue_priority_label ?? '',
      queue_depth_ahead: detail.derived.queue_depth_ahead ?? null,
      capacity_status: detail.derived.capacity_status ?? '',
      pool_concurrency_limit: detail.derived.pool_concurrency_limit ?? null,
      pool_slots_used: detail.derived.pool_slots_used ?? null,
    };
    watchTask(task);
    void syncTask(task);
  });
}, { immediate: true });
</script>
