<template>
  <div>
    <template v-if="!hasOrg">
      <div style="padding: 48px; text-align: center">
        <n-empty :description="t('user.noOrganization')" />
      </div>
    </template>

    <template v-else-if="error">
      <div style="padding: 48px">
        <n-result
          status="error"
          :title="t('common.loadResourcesFailed')"
          :description="error.message || t('common.pleaseTryAgain')"
        />
      </div>
    </template>

    <template v-else-if="isLoading">
      <div style="padding: 48px; display: flex; justify-content: center">
        <n-spin size="large" />
      </div>
    </template>

    <template v-else>
      <slot />
    </template>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";

defineProps<{
  isLoading: boolean;
  hasOrg: boolean;
  error?: Error | null;
}>();
const { t } = useI18n();
</script>
