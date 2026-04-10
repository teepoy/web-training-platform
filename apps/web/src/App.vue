<template>
  <n-config-provider :theme="computedTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-notification-provider>
        <n-dialog-provider>
          <template v-if="isAuthPage">
            <RouterView />
          </template>
          <n-layout v-else has-sider style="height: 100vh">
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
                <OrgSelector v-if="authStore.isAuthenticated" />
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
                  >{{ userInitials }}</n-avatar>
                </n-dropdown>
              </n-layout-header>
              <n-layout-content style="padding: 24px; overflow-y: auto">
                <RouterView />
                <n-back-top />
              </n-layout-content>
            </n-layout>
          </n-layout>
        </n-dialog-provider>
      </n-notification-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter, useRoute, RouterView } from 'vue-router'
import { darkTheme, type GlobalThemeOverrides } from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import { useUiStore } from './stores/ui'
import { useAuthStore } from './stores/auth'
import { useOrgStore } from './stores/org'
import OrgSelector from './components/OrgSelector.vue'

const router = useRouter()
const route = useRoute()
const uiStore = useUiStore()
const authStore = useAuthStore()
const orgStore = useOrgStore()
const queryClient = useQueryClient()

const AUTH_PATHS = ['/login', '/register']
const isAuthPage = computed(() => AUTH_PATHS.includes(route.path))

// Always use dark theme for auth pages (they have dark gradient background)
const computedTheme = computed(() => {
  if (isAuthPage.value) return darkTheme
  return uiStore.darkMode ? darkTheme : null
})

const themeOverrides: GlobalThemeOverrides = {
  common: {
    fontSizeMedium: '13px',
    fontSizeSmall: '12px',
    borderRadius: '8px',
  },
}

const activeRoute = computed(() => route.path)

// Check if current user is an admin (superadmin)
const isAdmin = computed(() => authStore.user?.is_superadmin ?? false)

// External service URLs - these can be configured via environment variables in production
const labelStudioUrl = 'http://localhost:8080'
const prefectUrl = 'http://localhost:4200'
const minioUrl = 'http://localhost:9001'
const pgAdminUrl = 'http://localhost:5050'

const menuOptions = [
  { label: 'Dashboard', key: '/dashboard' },
  { label: 'Datasets', key: '/datasets' },
  { label: 'Training Jobs', key: '/jobs' },
  { label: 'Models', key: '/models' },
  { label: 'Presets', key: '/presets' },
  { label: 'Schedules', key: '/schedules' },
]

const userInitials = computed(() =>
  authStore.user?.name?.slice(0, 2).toUpperCase() ?? 'LU'
)

const avatarDropdownOptions = computed(() => [
  { label: authStore.user?.name || 'Local User', key: 'name', disabled: true },
  { type: 'divider', key: 'd1' },
  { label: 'Profile', key: 'profile', disabled: true },
  { label: 'Logout', key: 'logout' },
])

function handleAvatarSelect(key: string) {
  if (key === 'logout') {
    authStore.logout()
    router.push('/login')
  }
}

onMounted(async () => {
  await authStore.initFromStorage()
  orgStore.initFromStorage()
  orgStore._queryClient = queryClient
  if (authStore.isAuthenticated) {
    try {
      await orgStore.fetchOrganizations()
    } catch {
      // org fetch will happen after login
    }
  }
})
</script>
