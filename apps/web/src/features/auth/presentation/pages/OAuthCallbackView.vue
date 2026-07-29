<template>
  <div class="auth-page" :style="themeStyleVars">
    <n-card class="auth-card">
      <n-spin v-if="processing" size="large" />
      <n-result
        v-else-if="errorMessage"
        status="error"
        title="Authentication Failed"
        :description="errorMessage"
      >
        <template #footer>
          <n-button @click="router.push('/login')">Back to Login</n-button>
        </template>
      </n-result>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useOrgStore } from "@/features/auth/application/org";
import { useAuthStore } from "@/features/auth/application/store";
import { useThemeVars } from "naive-ui";

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();
const orgStore = useOrgStore();
const themeVars = useThemeVars();
const themeStyleVars = computed(() => ({
  "--auth-bg-start": themeVars.value.bodyColor,
  "--auth-bg-mid": themeVars.value.cardColor,
  "--auth-bg-end": themeVars.value.modalColor,
  "--auth-shadow": themeVars.value.boxShadow1,
}));

const processing = ref(true);
const errorMessage = ref<string | null>(null);

onMounted(async () => {
  const raw = route.query.token;
  const token = Array.isArray(raw) ? raw[0] : raw;

  if (!token) {
    errorMessage.value = "No authentication token received. Please try logging in again.";
    processing.value = false;
    return;
  }

  try {
    await authStore.oauthLogin(token);
    await orgStore.fetchOrganizations();
    router.replace("/datasets");
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "OAuth authentication failed";
    errorMessage.value = msg;
    processing.value = false;
  }
});
</script>

<style scoped>
.auth-page {
  display: flex;
  min-height: 100vh;
  align-items: center;
  justify-content: center;
  background: linear-gradient(
    135deg,
    var(--auth-bg-start) 0%,
    var(--auth-bg-mid) 50%,
    var(--auth-bg-end) 100%
  );
}

.auth-card {
  width: 360px;
  border-radius: 12px;
  box-shadow: var(--auth-shadow);
}
</style>
