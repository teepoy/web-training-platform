<template>
  <n-layout has-sider style="height: 100vh">
    <n-layout-sider
      bordered
      show-trigger
      collapse-mode="width"
      :collapsed-width="64"
      :width="240"
      :collapsed="collapsed"
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <n-menu
        :collapsed="collapsed"
        :options="menuOptions"
        :value="activeRoute"
        @update:value="(key: string) => router.push(key)"
      />
    </n-layout-sider>
    <n-layout vertical>
      <n-layout-header
        bordered
        style="
          height: 48px;
          display: flex;
          align-items: center;
          padding: 0 16px;
          justify-content: space-between;
        "
      >
        <span style="font-weight: 600">{{ t("admin.title") }}</span>
        <n-button text type="primary" @click="router.push('/library')">
          ← {{ t("common.backToApp") }}
        </n-button>
      </n-layout-header>
      <n-layout-content style="padding: 24px; overflow-y: auto">
        <RouterView />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";

const router = useRouter();
const route = useRoute();
const { t } = useI18n();

const collapsed = ref(false);

const menuOptions = computed(() => [
  { label: t("admin.dashboard"), key: "/admin/dashboard" },
  { label: t("admin.infrastructure"), key: "/admin/infrastructure" },
]);

const activeRoute = computed(() => route.path);
</script>
