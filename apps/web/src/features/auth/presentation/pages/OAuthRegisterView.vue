<template>
  <div class="auth-page">
    <n-card class="auth-card" title="Complete Registration">
      <n-form
        ref="formRef"
        :model="formData"
        :rules="rules"
        @keyup.enter="handleSubmit"
      >
        <n-form-item label="Email" path="email">
          <n-input
            :value="formData.email"
            type="text"
            disabled
          />
        </n-form-item>
        <n-form-item label="Name" path="name">
          <n-input
            v-model:value="formData.name"
            type="text"
            placeholder="Your name"
            :disabled="loading"
          />
        </n-form-item>
        <n-button
          type="primary"
          block
          :loading="loading"
          @click="handleSubmit"
        >
          Complete Registration
        </n-button>
      </n-form>
      <n-result
        v-if="errorMessage"
        status="error"
        :title="errorMessage"
        size="small"
      >
        <template #footer>
          <n-button size="small" @click="router.push('/login')">
            Back to Login
          </n-button>
        </template>
      </n-result>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMessage, type FormInst, type FormRules } from 'naive-ui'
import { useAuthStore } from '@/features/auth/application/store'
import { useOrgStore } from '@/features/auth/application/org'
import { authOAuthRegister } from '../../infrastructure/api'

const router = useRouter()
const route = useRoute()
const message = useMessage()
const authStore = useAuthStore()
const orgStore = useOrgStore()

const formRef = ref<FormInst | null>(null)
const loading = ref(false)
const errorMessage = ref<string | null>(null)

function getQueryParam(key: string): string {
  const raw = route.query[key]
  return (Array.isArray(raw) ? raw[0] : raw) ?? ''
}

const stateToken = getQueryParam('state_token')
const emailFromOAuth = getQueryParam('email')
const nameFromOAuth = getQueryParam('name')

const formData = ref({
  email: emailFromOAuth,
  name: nameFromOAuth,
})

const rules: FormRules = {
  name: [{ required: true, message: 'Name is required', trigger: 'blur' }],
}

onMounted(() => {
  if (!stateToken) {
    errorMessage.value =
      'Missing registration token. Please start the login flow again.'
  }
})

async function handleSubmit() {
  if (!stateToken) return

  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  errorMessage.value = null
  try {
    const resp = await authOAuthRegister({
      state_token: stateToken,
      name: formData.value.name,
    })
    await authStore.oauthLogin(resp.access_token)
    await orgStore.fetchOrganizations()
    router.replace('/datasets')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Registration failed'
    message.error(msg)
    errorMessage.value = msg
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
</style>
