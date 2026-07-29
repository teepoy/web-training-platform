<template>
  <div class="auth-page" :style="themeStyleVars">
    <n-card class="auth-card" title="Complete Registration">
      <n-form ref="formRef" :model="formData" :rules="rules" @keyup.enter="handleSubmit">
        <n-form-item label="Email" path="email">
          <n-input :value="formData.email" type="text" disabled />
        </n-form-item>
        <n-form-item label="Name" path="name">
          <n-input
            v-model:value="formData.name"
            type="text"
            placeholder="Your name"
            :disabled="registerMutation.isPending.value"
          />
        </n-form-item>
        <n-button
          type="primary"
          block
          :loading="registerMutation.isPending.value"
          @click="handleSubmit"
        >
          Complete Registration
        </n-button>
      </n-form>
      <n-result v-if="errorMessage" status="error" :title="errorMessage" size="small">
        <template #footer>
          <n-button size="small" @click="router.push('/login')"> Back to Login </n-button>
        </template>
      </n-result>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useMessage, useThemeVars, type FormInst, type FormRules } from "naive-ui";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { useOauthRegisterApiV1AuthOauthRegisterPost } from "@/generated/orval/endpoints/api";
import type { LoginResponse } from "@/generated/orval/models";

const router = useRouter();
const route = useRoute();
const message = useMessage();
const authStore = useAuthStore();
const orgStore = useOrgStore();
const themeVars = useThemeVars();
const themeStyleVars = computed(() => ({
  "--auth-bg-start": themeVars.value.bodyColor,
  "--auth-bg-mid": themeVars.value.cardColor,
  "--auth-bg-end": themeVars.value.modalColor,
  "--auth-shadow": themeVars.value.boxShadow1,
}));

const formRef = ref<FormInst | null>(null);
const errorMessage = ref<string | null>(null);

const registerMutation = useOauthRegisterApiV1AuthOauthRegisterPost();

function getQueryParam(key: string): string {
  const raw = route.query[key];
  return (Array.isArray(raw) ? raw[0] : raw) ?? "";
}

const stateToken = getQueryParam("state_token");
const emailFromOAuth = getQueryParam("email");
const nameFromOAuth = getQueryParam("name");

const formData = ref({
  email: emailFromOAuth,
  name: nameFromOAuth,
});

const rules: FormRules = {
  name: [{ required: true, message: "Name is required", trigger: "blur" }],
};

onMounted(() => {
  if (!stateToken) {
    errorMessage.value = "Missing registration token. Please start the login flow again.";
  }
});

async function handleSubmit() {
  if (!stateToken) return;

  try {
    await formRef.value?.validate();
  } catch {
    return;
  }

  errorMessage.value = null;
  try {
    const loginResp = await registerMutation.mutateAsync({
      data: {
        state_token: stateToken,
        name: formData.value.name,
      },
    });
    await authStore.oauthLogin(loginResp.access_token);
    await orgStore.fetchOrganizations();
    router.replace("/datasets");
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Registration failed";
    message.error(msg);
    errorMessage.value = msg;
  }
}
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
