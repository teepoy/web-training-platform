<template>
  <div class="auth-page">
    <n-card class="auth-card" title="Sign In">
      <n-form ref="formRef" :model="formData" :rules="rules" @keyup.enter="handleSubmit">
        <n-form-item label="Email" path="email">
          <n-input
            v-model:value="formData.email"
            type="text"
            placeholder="you@example.com"
            :disabled="loading"
          />
        </n-form-item>
        <n-form-item label="Password" path="password">
          <n-input
            v-model:value="formData.password"
            type="password"
            placeholder="Password"
            show-password-on="click"
            :disabled="loading"
          />
        </n-form-item>
        <n-button
          type="primary"
          block
          :loading="loading"
          @click="handleSubmit"
        >
          Sign In
        </n-button>
      </n-form>
      <div v-if="oauthProviders.length > 0" class="oauth-section">
        <div class="oauth-divider">
          <span class="oauth-divider-text">or continue with</span>
        </div>
        <div v-for="prov in oauthProviders" :key="prov.id" class="oauth-button-wrapper">
          <n-button
            secondary
            block
            tag="a"
            :href="`${API_BASE}/auth/oauth/${prov.id}`"
          >
            Continue with {{ prov.display_name }}
          </n-button>
        </div>
      </div>
      <div class="auth-link">
        Don't have an account?
        <router-link to="/register">Register</router-link>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, type FormInst, type FormRules } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import { API_BASE } from '@platform/web-ui/api'
import { fetchOAuthProviders, type OAuthProviderInfo } from '@platform/web-ui/api/auth'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

import { useOrgStore } from '../stores/org'
const orgStore = useOrgStore()

const formRef = ref<FormInst | null>(null)
const loading = ref(false)
const oauthProviders = ref<OAuthProviderInfo[]>([])

onMounted(async () => {
  try {
    oauthProviders.value = await fetchOAuthProviders()
  } catch {
    // Graceful degradation: no OAuth buttons shown
  }
})

const formData = ref({
  email: '',
  password: '',
})

const rules: FormRules = {
  email: [{ required: true, message: 'Email is required', trigger: 'blur' }],
  password: [{ required: true, message: 'Password is required', trigger: 'blur' }],
}

async function handleSubmit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await authStore.login(formData.value.email, formData.value.password)
    await orgStore.fetchOrganizations()
    router.push('/datasets')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Login failed'
    message.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  display: flex;
  min-height: 100vh;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
}

.auth-card {
  width: 360px;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
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
  color: rgba(255, 255, 255, 0.35);
  font-size: 12px;
}

.oauth-divider::before,
.oauth-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: rgba(255, 255, 255, 0.12);
}

.oauth-divider-text {
  padding: 0 12px;
}

.oauth-button-wrapper {
  margin-top: 8px;
}
</style>
