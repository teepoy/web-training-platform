<script setup lang="ts">
import { computed } from "vue";
import { useRouter, useRoute, RouterView } from "vue-router";
import { useI18n } from "vue-i18n";

const router = useRouter();
const route = useRoute();
const { t } = useI18n();

const menuOptions = computed(() => [
  { label: t("settings.accessKeys"), key: "/settings/access-keys" },
]);

const activeRoute = computed(() => route.path);

function handleMenuSelect(key: string) {
  router.push(key);
}

function handleBack() {
  router.push("/datasets");
}
</script>

<template>
  <n-layout has-sider style="height: 100vh">
    <n-layout-sider bordered :width="240">
      <n-menu :options="menuOptions" :value="activeRoute" @update:value="handleMenuSelect" />
    </n-layout-sider>

    <n-layout vertical>
      <n-layout-header
        bordered
        style="height: 48px; display: flex; align-items: center; padding: 0 16px; gap: 12px"
      >
        <span style="font-weight: 600; flex: 1">{{ t("settings.title") }}</span>
        <n-button text type="primary" size="small" @click="handleBack">
          &larr; {{ t("common.backToApp") }}
        </n-button>
      </n-layout-header>

      <n-layout-content style="padding: 24px; overflow-y: auto">
        <RouterView />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>
