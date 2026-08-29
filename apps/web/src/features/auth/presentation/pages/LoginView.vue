<template>
  <div class="auth-page" :style="themeStyleVars">
    <n-card class="auth-card" :title="t('auth.signIn')" data-testid="login-form">
      <n-form ref="formRef" :model="formData" :rules="rules" @keyup.enter="handleSubmit">
        <n-form-item :label="t('common.email')" path="email">
          <n-input
            v-model:value="formData.email"
            type="text"
            placeholder="you@example.com"
            :disabled="loading"
            data-testid="login-email"
          />
        </n-form-item>
        <n-form-item :label="t('common.password')" path="password">
          <n-input
            v-model:value="formData.password"
            type="password"
            :placeholder="t('common.password')"
            show-password-on="click"
            :disabled="loading"
            data-testid="login-password"
          />
        </n-form-item>
        <n-button
          type="primary"
          block
          :loading="loading"
          data-testid="login-submit"
          @click="handleSubmit"
        >
          {{ t("auth.signIn") }}
        </n-button>
      </n-form>
      <div v-if="(oauthProviders ?? []).length > 0" class="oauth-section">
        <div class="oauth-divider">
          <span class="oauth-divider-text">{{ t("auth.orContinueWith") }}</span>
        </div>
        <div v-for="prov in oauthProviders" :key="prov.id" class="oauth-button-wrapper">
          <n-button secondary block tag="a" :href="`${API_BASE}/auth/oauth/${prov.id}`">
            {{ t("auth.continueWith", { provider: prov.display_name }) }}
          </n-button>
        </div>
      </div>
      <div class="auth-link">
        {{ t("auth.noAccount") }}
        <router-link to="/register">{{ t("auth.register") }}</router-link>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { useMessage, useThemeVars, type FormInst, type FormRules } from "naive-ui";
import { useAuthStore } from "@/features/auth/application/store";
import { API_BASE } from "@/shared/api/client";
import { useListOauthProvidersApiV1AuthOauthProvidersGet } from "@/generated/orval/endpoints/api";
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
  "--auth-divider": themeVars.value.dividerColor,
  "--auth-text-muted": themeVars.value.textColor3,
  "--auth-shadow": themeVars.value.boxShadow1,
}));

import { useOrgStore } from "@/features/auth/application/org";
const orgStore = useOrgStore();

const formRef = ref<FormInst | null>(null);
const loading = ref(false);

const { data: oauthProviders } = useListOauthProvidersApiV1AuthOauthProvidersGet({
  query: {},
});

const formData = ref({
  email: "",
  password: "",
});

const rules = computed<FormRules>(() => ({
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
    await authStore.login(formData.value.email, formData.value.password);
    await orgStore.fetchOrganizations();
    router.push("/library");
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : t("auth.loginFailed");
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

.oauth-section {
  margin-top: 20px;
}

.oauth-divider {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  color: var(--auth-text-muted);
  font-size: 12px;
}

.oauth-divider::before,
.oauth-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--auth-divider);
}

.oauth-divider-text {
  padding: 0 12px;
}

.oauth-button-wrapper {
  margin-top: 8px;
}
</style>
