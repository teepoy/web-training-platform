<template>
  <div class="auth-page" :style="themeStyleVars">
    <n-card class="auth-card" :title="t('auth.createAccount')" data-testid="register-form">
      <n-form ref="formRef" :model="formData" :rules="rules" @keyup.enter="handleSubmit">
        <n-form-item :label="t('common.name')" path="name">
          <n-input
            v-model:value="formData.name"
            type="text"
            :placeholder="t('auth.yourName')"
            :disabled="loading"
            data-testid="register-name"
          />
        </n-form-item>
        <n-form-item :label="t('common.email')" path="email">
          <n-input
            v-model:value="formData.email"
            type="text"
            placeholder="you@example.com"
            :disabled="loading"
            data-testid="register-email"
          />
        </n-form-item>
        <n-form-item :label="t('common.password')" path="password">
          <n-input
            v-model:value="formData.password"
            type="password"
            :placeholder="t('common.password')"
            show-password-on="click"
            :disabled="loading"
            data-testid="register-password"
          />
        </n-form-item>
        <n-button
          type="primary"
          block
          :loading="loading"
          data-testid="register-submit"
          @click="handleSubmit"
        >
          {{ t("auth.createAccount") }}
        </n-button>
      </n-form>
      <div class="auth-link">
        {{ t("auth.haveAccount") }}
        <router-link to="/login">{{ t("auth.login") }}</router-link>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { useMessage, useThemeVars, type FormInst, type FormRules } from "naive-ui";
import { useAuthStore } from "@/features/auth/application/store";
import { useI18n } from "vue-i18n";

const router = useRouter();
const message = useMessage();
const authStore = useAuthStore();
const { t } = useI18n();
const themeVars = useThemeVars();
const themeStyleVars = computed(() => ({
  "--auth-bg-start": themeVars.value.bodyColor,
  "--auth-bg-mid": themeVars.value.cardColor,
  "--auth-bg-end": themeVars.value.modalColor,
  "--auth-shadow": themeVars.value.boxShadow1,
}));

import { useOrgStore } from "@/features/auth/application/org";
const orgStore = useOrgStore();

const formRef = ref<FormInst | null>(null);
const loading = ref(false);

const formData = ref({
  name: "",
  email: "",
  password: "",
});

const rules = computed<FormRules>(() => ({
  name: [
    { required: true, message: t("common.required", { field: t("common.name") }), trigger: "blur" },
  ],
  email: [
    {
      required: true,
      message: t("common.required", { field: t("common.email") }),
      trigger: "blur",
    },
  ],
  password: [
    {
      required: true,
      message: t("common.required", { field: t("common.password") }),
      trigger: "blur",
    },
  ],
}));

async function handleSubmit() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  loading.value = true;
  try {
    await authStore.register(formData.value.name, formData.value.email, formData.value.password);
    await orgStore.fetchOrganizations();
    router.push("/library");
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : t("auth.registrationFailed");
    message.error(msg);
  } finally {
    loading.value = false;
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

.auth-link {
  margin-top: 16px;
  text-align: center;
  font-size: 13px;
}
</style>
